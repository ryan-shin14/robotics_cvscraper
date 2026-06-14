"""
Shared data models used across the pipeline.
Everything is a plain dataclass so it serialises cleanly to JSON.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional
import json


@dataclass
class GitHubUser:
    """Minimal GitHub user record discovered during search."""
    login: str
    name: str
    company: str          # raw value from GitHub profile
    bio: str
    blog: str             # personal website / GitHub Pages URL
    location: str
    html_url: str
    avatar_url: str
    public_repos: int
    matched_company: str  # which TARGET_COMPANY triggered this result
    matched_keyword: str  # which ROLE_KEYWORD triggered this result


@dataclass
class CVSource:
    """A discovered CV file (PDF or HTML) before parsing."""
    user_login: str
    source_type: str      # "github_pages" | "personal_site" | "repo_file"
    url: str
    file_type: str        # "pdf" | "html"
    raw_path: Optional[str] = None   # local path after download


@dataclass
class Education:
    school: str = ""
    degree: str = ""
    field: str = ""
    years: str = ""


@dataclass
class Experience:
    company: str = ""
    title: str = ""
    duration: str = ""
    is_internship: bool = False
    description: str = ""


@dataclass
class ParsedCV:
    """Structured career data extracted from a CV."""
    user_login: str
    source_url: str
    name: str = ""
    email: str = ""
    github: str = ""
    website: str = ""
    summary: str = ""
    education: list[Education] = field(default_factory=list)
    experience: list[Experience] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    publications: list[str] = field(default_factory=list)
    raw_text_snippet: str = ""   # first 500 chars of raw text for debugging
    parse_error: str = ""
    matched_company: str = ""
    matched_keyword: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)
