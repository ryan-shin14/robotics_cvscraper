"""
CV Fetcher
==========
Given a list of candidate URLs (personal sites, GitHub Pages), this module:

1. Fetches the root page and looks for links to CV/resume files (PDF or HTML).
2. Also checks GitHub repos for files whose names match CV patterns.
3. Downloads matched files to data/raw/.

Respects rate limits and never touches pages that require login.
"""

from __future__ import annotations

import re
import sys
import time
import hashlib
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
from config import (
    DATA_RAW, CV_FETCH_DELAY, MAX_CV_BYTES,
    CV_FILENAME_PATTERNS, CV_EXTENSIONS,
)
from models import GitHubUser, CVSource
from logger import get_logger

log = get_logger("cv_fetcher")

GITHUB_RAW = "https://raw.githubusercontent.com/{login}/{repo}/{branch}/{path}"
GITHUB_REPO_CONTENTS = "https://api.github.com/repos/{login}/{repo}/contents"
GITHUB_USER_REPOS    = "https://api.github.com/users/{login}/repos"

HEADERS = {
    "User-Agent": (
        "robotics-career-research-bot/1.0 "
        "(public CV data only; contact: see repo)"
    )
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_cv_filename(name: str) -> bool:
    name_lower = name.lower()
    stem = Path(name_lower).stem
    ext  = Path(name_lower).suffix
    return (
        ext in CV_EXTENSIONS
        and any(pat in stem for pat in CV_FILENAME_PATTERNS)
    )


def _safe_get(url: str, stream: bool = False, timeout: int = 15) -> Optional[requests.Response]:
    try:
        resp = requests.get(url, headers=HEADERS, stream=stream, timeout=timeout, allow_redirects=True)
        if resp.status_code == 200:
            return resp
        log.debug(f"  HTTP {resp.status_code}: {url}")
    except requests.RequestException as exc:
        log.debug(f"  Fetch error ({exc}): {url}")
    return None


def _url_to_filename(url: str) -> str:
    """Deterministic local filename from URL."""
    h = hashlib.md5(url.encode()).hexdigest()[:8]
    parsed = urlparse(url)
    ext = Path(parsed.path).suffix or ".bin"
    return f"{h}{ext}"


def _download(url: str, dest: Path) -> bool:
    """Download url → dest. Returns True on success."""
    if dest.exists():
        log.debug(f"  Already downloaded: {dest.name}")
        return True

    resp = _safe_get(url, stream=True)
    if not resp:
        return False

    content_len = int(resp.headers.get("Content-Length", 0))
    if content_len and content_len > MAX_CV_BYTES:
        log.debug(f"  Skipping (too large: {content_len/1e6:.1f} MB): {url}")
        return False

    data = b""
    for chunk in resp.iter_content(chunk_size=8192):
        data += chunk
        if len(data) > MAX_CV_BYTES:
            log.debug(f"  Skipping (exceeded size limit): {url}")
            return False

    dest.write_bytes(data)
    log.debug(f"  Saved {len(data)/1024:.1f} KB → {dest.name}")
    return True


# ── Site scraping ─────────────────────────────────────────────────────────────

def _find_cv_links_in_page(base_url: str, html: str) -> list[str]:
    """
    Parse HTML, return absolute URLs that look like CV/resume links
    (either by filename or by link text).
    """
    soup = BeautifulSoup(html, "lxml")
    cv_urls: list[str] = []

    cv_text_re = re.compile(
        r"\b(cv|resume|curriculum.vitae)\b", re.IGNORECASE
    )

    for a in soup.find_all("a", href=True):
        href: str = a["href"].strip()
        text: str = a.get_text(strip=True)

        # Skip anchors, mailto, javascript
        if href.startswith(("#", "mailto:", "javascript:")):
            continue

        abs_url = urljoin(base_url, href)
        parsed  = urlparse(abs_url)

        # Match by filename
        if _is_cv_filename(Path(parsed.path).name):
            cv_urls.append(abs_url)
            continue

        # Match by link text or href containing cv/resume keywords
        if cv_text_re.search(text) or cv_text_re.search(href):
            ext = Path(parsed.path).suffix.lower()
            if ext in CV_EXTENSIONS or not ext:
                cv_urls.append(abs_url)

    return list(dict.fromkeys(cv_urls))   # deduplicate, preserve order


def _scrape_site(base_url: str) -> list[str]:
    """
    Fetch base_url, search for CV links.
    Also tries common paths like /resume, /cv, /resume.pdf, etc.
    """
    found: list[str] = []

    resp = _safe_get(base_url)
    if resp:
        found.extend(_find_cv_links_in_page(base_url, resp.text))

    # Probe well-known paths
    guesses = []
    for pat in CV_FILENAME_PATTERNS:
        for ext in CV_EXTENSIONS:
            guesses.append(f"{pat}{ext}")
        guesses.append(pat)   # directory / HTML page

    for guess in guesses:
        url = urljoin(base_url.rstrip("/") + "/", guess)
        if url not in found:
            r = _safe_get(url)
            if r:
                ct = r.headers.get("Content-Type", "")
                if "pdf" in ct or "html" in ct or "text" in ct:
                    found.append(url)

    return found


# ── GitHub repo search ────────────────────────────────────────────────────────

def _search_github_repos(login: str, token: str) -> list[str]:
    """
    List the user's public repos, look for CV-named files in the root.
    Returns raw GitHub URLs for matching files.
    """
    headers = {
        **HEADERS,
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    found: list[str] = []

    # Get repo list
    resp = requests.get(
        GITHUB_USER_REPOS.format(login=login),
        headers=headers,
        params={"per_page": 100, "sort": "updated"},
        timeout=15,
    )
    if resp.status_code != 200:
        return found

    repos = resp.json()

    for repo in repos:
        repo_name    = repo["name"]
        default_branch = repo.get("default_branch", "main")

        # Repos whose names suggest a CV/portfolio
        is_cv_repo = any(
            pat in repo_name.lower() for pat in [*CV_FILENAME_PATTERNS, "portfolio", "website"]
        )

        # Fetch root contents
        contents_url = GITHUB_REPO_CONTENTS.format(login=login, repo=repo_name)
        cr = requests.get(
            contents_url,
            headers=headers,
            params={"ref": default_branch},
            timeout=15,
        )
        if cr.status_code != 200:
            continue

        for item in cr.json():
            if item["type"] != "file":
                continue
            if _is_cv_filename(item["name"]) or (is_cv_repo and _is_cv_filename(item["name"])):
                raw_url = GITHUB_RAW.format(
                    login=login,
                    repo=repo_name,
                    branch=default_branch,
                    path=item["path"],
                )
                found.append(raw_url)

        time.sleep(0.3)

    return found


# ── Public entry point ────────────────────────────────────────────────────────

def fetch_cvs_for_user(
    user: GitHubUser,
    candidate_urls: list[tuple[str, str]],
    github_token: str,
) -> list[CVSource]:
    """
    Find and download all discoverable CVs for a single GitHub user.
    Returns CVSource records for each successfully downloaded file.
    """
    out_dir = DATA_RAW / user.login
    out_dir.mkdir(parents=True, exist_ok=True)

    sources: list[CVSource] = []
    seen_urls: set[str] = set()

    def _register(url: str, source_type: str, file_type: str):
        if url in seen_urls:
            return
        seen_urls.add(url)

        fname    = _url_to_filename(url)
        dest     = out_dir / fname
        ok       = _download(url, dest)
        if ok:
            sources.append(CVSource(
                user_login=user.login,
                source_type=source_type,
                url=url,
                file_type=file_type,
                raw_path=str(dest),
            ))

    # 1. Probe personal sites / GitHub Pages
    for base_url, stype in candidate_urls:
        log.debug(f"  Probing {stype}: {base_url}")
        cv_links = _scrape_site(base_url)
        for link in cv_links:
            ext = Path(urlparse(link).path).suffix.lower()
            ftype = "pdf" if ext == ".pdf" else "html"
            _register(link, stype, ftype)
            time.sleep(CV_FETCH_DELAY)

    # 2. Search GitHub repos
    log.debug(f"  Searching GitHub repos for {user.login}")
    repo_urls = _search_github_repos(user.login, github_token)
    for url in repo_urls:
        ext   = Path(urlparse(url).path).suffix.lower()
        ftype = "pdf" if ext == ".pdf" else "html"
        _register(url, "repo_file", ftype)
        time.sleep(CV_FETCH_DELAY)

    if sources:
        log.info(f"  {user.login}: downloaded {len(sources)} CV file(s)")
    else:
        log.debug(f"  {user.login}: no CV files found")

    return sources
