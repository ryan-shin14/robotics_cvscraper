"""
Robotics CV Scraper — Main Orchestrator
========================================

Usage:
    python main.py [--discover] [--fetch] [--parse] [--analyse] [--all]

Steps:
    1. discover  — find GitHub users matching target companies + roles
    2. fetch     — download CV files from their personal sites / repos
    3. parse     — extract structured data from CVs using Claude
    4. analyse   — aggregate and print career-path report

Environment variables (see .env.example):
    GITHUB_TOKEN        — required for GitHub API (free, no billing needed)
    ANTHROPIC_API_KEY   — required for Claude parsing (optional; text-only without it)
"""

from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()
import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

# Allow running from src/ or from project root
sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from config import DATA_RAW, DATA_OUT
from logger import get_logger
from models import GitHubUser, CVSource, ParsedCV
from github_discovery import discover_users, candidate_cv_urls
from cv_fetcher import fetch_cvs_for_user
from cv_parser import parse_cv
from analysis import load_parsed_cvs, analyse, print_report

log = get_logger("main")

# ── Persistence helpers ───────────────────────────────────────────────────────

USERS_CACHE  = DATA_RAW / "_users.json"
SOURCES_CACHE= DATA_RAW / "_sources.json"


def _save_users(users: list[GitHubUser]):
    USERS_CACHE.write_text(json.dumps([asdict(u) for u in users], indent=2))
    log.info(f"Saved {len(users)} users → {USERS_CACHE}")


def _load_users() -> list[GitHubUser]:
    if not USERS_CACHE.exists():
        return []
    data = json.loads(USERS_CACHE.read_text())
    return [GitHubUser(**d) for d in data]


def _save_sources(sources: list[CVSource]):
    SOURCES_CACHE.write_text(json.dumps([asdict(s) for s in sources], indent=2))
    log.info(f"Saved {len(sources)} sources → {SOURCES_CACHE}")


def _load_sources() -> list[CVSource]:
    if not SOURCES_CACHE.exists():
        return []
    data = json.loads(SOURCES_CACHE.read_text())
    return [CVSource(**d) for d in data]


def _cv_out_path(login: str, url: str) -> Path:
    slug = url.rstrip("/").split("/")[-1].split("?")[0][:40] or "cv"
    return DATA_OUT / f"{login}_{slug}.json"


# ── Pipeline steps ────────────────────────────────────────────────────────────

def step_discover(github_token: str) -> list[GitHubUser]:
    log.info("═" * 60)
    log.info("STEP 1 — GitHub User Discovery")
    log.info("═" * 60)
    users = discover_users(github_token)
    _save_users(users)
    return users


def step_fetch(users: list[GitHubUser], github_token: str) -> list[CVSource]:
    log.info("═" * 60)
    log.info("STEP 2 — CV Fetching")
    log.info("═" * 60)

    all_sources: list[CVSource] = []
    for i, user in enumerate(users, 1):
        log.info(f"[{i}/{len(users)}] {user.login} — {user.name}")
        candidates = candidate_cv_urls(user)
        sources    = fetch_cvs_for_user(user, candidates, github_token)
        all_sources.extend(sources)
        time.sleep(1)

    _save_sources(all_sources)
    log.info(f"Fetched {len(all_sources)} CV files total.")
    return all_sources


def step_parse(sources: list[CVSource], users: list[GitHubUser], anthropic_key: str):
    log.info("═" * 60)
    log.info("STEP 3 — CV Parsing via Claude")
    log.info("═" * 60)

    DATA_OUT.mkdir(parents=True, exist_ok=True)

    # Build lookup: login → user (for matched_company / matched_keyword)
    user_map = {u.login: u for u in users}

    parsed_count = 0
    for i, src in enumerate(sources, 1):
        out_path = _cv_out_path(src.user_login, src.url)
        if out_path.exists():
            log.info(f"[{i}/{len(sources)}] skip (cached): {out_path.name}")
            continue

        log.info(f"[{i}/{len(sources)}] Parsing: {src.user_login} | {src.url}")
        user = user_map.get(src.user_login)

        cv = parse_cv(
            src,
            api_key=anthropic_key,
            matched_company=user.matched_company if user else "",
            matched_keyword=user.matched_keyword if user else "",
        )
        out_path.write_text(cv.to_json())
        parsed_count += 1
        time.sleep(1)   # be gentle with Claude API

    log.info(f"Parsed {parsed_count} new CVs.")


def step_analyse():
    log.info("═" * 60)
    log.info("STEP 4 — Career-Path Analysis")
    log.info("═" * 60)

    cvs    = load_parsed_cvs()
    if not cvs:
        log.warning("No parsed CVs found in data/parsed/. Run --parse first.")
        return

    report = analyse(cvs)
    print_report(report)

    out = DATA_OUT / "analysis_report.json"
    out.write_text(json.dumps(report, indent=2))
    log.info(f"Full report saved → {out}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Robotics CV Scraper — career-path research from public GitHub CVs"
    )
    parser.add_argument("--discover", action="store_true", help="Run Step 1: GitHub user discovery")
    parser.add_argument("--fetch",    action="store_true", help="Run Step 2: Download CV files")
    parser.add_argument("--parse",    action="store_true", help="Run Step 3: Parse CVs with Claude")
    parser.add_argument("--analyse",  action="store_true", help="Run Step 4: Aggregate analysis")
    parser.add_argument("--all",      action="store_true", help="Run all steps end-to-end")
    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        sys.exit(0)

    github_token   = os.environ.get("GITHUB_TOKEN", "")
    anthropic_key  = os.environ.get("ANTHROPIC_API_KEY", "")

    if not github_token and (args.discover or args.fetch or args.all):
        log.error("GITHUB_TOKEN environment variable not set.")
        sys.exit(1)

    run_all = args.all

    # ── Discover ──
    if run_all or args.discover:
        users = step_discover(github_token)
    else:
        users = _load_users()
        log.info(f"Loaded {len(users)} cached users.")

    # ── Fetch ──
    if run_all or args.fetch:
        sources = step_fetch(users, github_token)
    else:
        sources = _load_sources()
        log.info(f"Loaded {len(sources)} cached CV sources.")

    # ── Parse ──
    if run_all or args.parse:
        step_parse(sources, users, anthropic_key)

    # ── Analyse ──
    if run_all or args.analyse:
        step_analyse()


if __name__ == "__main__":
    main()
