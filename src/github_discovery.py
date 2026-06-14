"""
GitHub Discovery
================
Uses the GitHub Search API to find engineers at target robotics companies
who have public GitHub profiles, then surfaces their personal sites /
GitHub Pages URLs for the CV scraper to follow up on.

Rate limits (authenticated):
  - Search API:  30 requests / minute
  - Core API:   5 000 requests / hour

Docs: https://docs.github.com/en/rest/search/search#search-users
"""

from __future__ import annotations

import time
import sys
from typing import Optional

import requests

# Allow running from src/ directly
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from config import TARGET_COMPANIES, ROLE_KEYWORDS, MAX_USERS_PER_QUERY, GITHUB_DELAY
from models import GitHubUser
from logger import get_logger

log = get_logger("github_discovery")

GITHUB_SEARCH_URL = "https://api.github.com/search/users"
GITHUB_USER_URL   = "https://api.github.com/users/{login}"


# ── Core search ───────────────────────────────────────────────────────────────

def _search_users(
    query: str,
    token: str,
    per_page: int = 30,
    page: int = 1,
) -> dict:
    """Raw call to the GitHub user-search endpoint."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    params = {"q": query, "per_page": per_page, "page": page}
    resp = requests.get(GITHUB_SEARCH_URL, headers=headers, params=params, timeout=15)

    if resp.status_code == 403:
        reset = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
        wait  = max(reset - int(time.time()), 5)
        log.warning(f"Rate-limited. Sleeping {wait}s …")
        time.sleep(wait)
        return _search_users(query, token, per_page, page)

    resp.raise_for_status()
    return resp.json()


def _get_user_detail(login: str, token: str) -> Optional[dict]:
    """Fetch full user profile (includes blog, company, bio, location)."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    resp = requests.get(
        GITHUB_USER_URL.format(login=login),
        headers=headers,
        timeout=15,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def _normalise_url(url: str) -> str:
    """Ensure the URL has a scheme."""
    if not url:
        return ""
    url = url.strip()
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


# ── Main discovery function ───────────────────────────────────────────────────

def discover_users(token: str) -> list[GitHubUser]:
    """
    Search GitHub for engineers at each target company × role keyword.
    Returns de-duplicated GitHubUser records.
    """
    seen_logins: set[str] = set()
    users: list[GitHubUser] = []

    for company in TARGET_COMPANIES:
        for keyword in ROLE_KEYWORDS:
            # GitHub user search supports: company:"X" in:bio keyword
            query = f'"{company}" "{keyword}" in:bio'
            log.info(f"Searching: {query!r}")

            try:
                result = _search_users(query, token, per_page=min(MAX_USERS_PER_QUERY, 30))
            except requests.HTTPError as exc:
                log.warning(f"Search failed ({exc}), skipping.")
                time.sleep(GITHUB_DELAY * 2)
                continue

            items = result.get("items", [])
            log.info(f"  → {len(items)} hits (total: {result.get('total_count', '?')})")

            for item in items[:MAX_USERS_PER_QUERY]:
                login = item["login"]
                if login in seen_logins:
                    continue
                seen_logins.add(login)

                time.sleep(GITHUB_DELAY)

                detail = _get_user_detail(login, token)
                if not detail:
                    continue

                user = GitHubUser(
                    login=login,
                    name=detail.get("name") or login,
                    company=detail.get("company") or "",
                    bio=detail.get("bio") or "",
                    blog=_normalise_url(detail.get("blog") or ""),
                    location=detail.get("location") or "",
                    html_url=detail.get("html_url") or f"https://github.com/{login}",
                    avatar_url=detail.get("avatar_url") or "",
                    public_repos=detail.get("public_repos") or 0,
                    matched_company=company,
                    matched_keyword=keyword,
                )
                users.append(user)
                log.debug(f"  + {login} | company={user.company!r} | blog={user.blog!r}")

            time.sleep(GITHUB_DELAY)

    log.info(f"Discovery complete — {len(users)} unique users found.")
    return users


# ── CV URL candidates for a user ──────────────────────────────────────────────

def candidate_cv_urls(user: GitHubUser) -> list[tuple[str, str]]:
    """
    Return (url, source_type) pairs to try for this user's CV.
    Checks:
      1. GitHub Pages site (login.github.io)
      2. Personal blog / website listed on their profile
    The CV fetcher will probe these URLs for actual CV files.
    """
    candidates: list[tuple[str, str]] = []

    # GitHub Pages root
    pages_url = f"https://{user.login}.github.io"
    candidates.append((pages_url, "github_pages"))

    # Personal site listed on profile
    if user.blog and user.blog != pages_url:
        candidates.append((user.blog, "personal_site"))

    return candidates


if __name__ == "__main__":
    import os, json
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("Set GITHUB_TOKEN env var first.")
        raise SystemExit(1)

    found = discover_users(token)
    print(json.dumps([u.__dict__ for u in found[:3]], indent=2))
