"""
CV Parser
=========
Given a downloaded CV file (PDF or HTML), this module:

1. Extracts raw text (pdfplumber for PDFs, BeautifulSoup for HTML).
2. Sends the text to Claude to extract structured career data.
3. Returns a ParsedCV dataclass.

Claude is called via the REST API — no SDK required.
"""

from __future__ import annotations

import json
import os
import sys
import re
import time
from pathlib import Path
from typing import Optional

import requests
import pdfplumber
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
from config import CLAUDE_API_URL, CLAUDE_MODEL, CLAUDE_MAX_TOKENS
from models import CVSource, ParsedCV, Education, Experience
from logger import get_logger

log = get_logger("cv_parser")

# ── Text extraction ───────────────────────────────────────────────────────────

def _extract_text_pdf(path: str) -> str:
    """Extract all text from a PDF file using pdfplumber."""
    text_parts: list[str] = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
    except Exception as exc:
        log.warning(f"pdfplumber error on {path}: {exc}")
    return "\n".join(text_parts)


def _extract_text_html(path: str) -> str:
    """Extract readable text from an HTML file."""
    try:
        html = Path(path).read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(html, "lxml")
        # Remove script / style noise
        for tag in soup(["script", "style", "nav", "footer", "head"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)
    except Exception as exc:
        log.warning(f"HTML parse error on {path}: {exc}")
        return ""


def extract_text(source: CVSource) -> str:
    """Dispatch to the right extractor based on file_type."""
    if not source.raw_path or not Path(source.raw_path).exists():
        log.warning(f"File not found: {source.raw_path}")
        return ""

    if source.file_type == "pdf":
        return _extract_text_pdf(source.raw_path)
    else:
        return _extract_text_html(source.raw_path)


# ── Claude API call ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a precise career-data extraction assistant.
Given raw text from an engineering CV/resume, extract structured data.
Respond ONLY with a single valid JSON object — no markdown fences, no commentary.

JSON schema (use empty string / empty list when data is absent):
{
  "name": "string",
  "email": "string",
  "github": "string",
  "website": "string",
  "summary": "string (brief professional summary, max 3 sentences)",
  "education": [
    {
      "school": "string",
      "degree": "string (e.g. BS, MS, PhD)",
      "field": "string (e.g. Mechanical Engineering)",
      "years": "string (e.g. 2018–2022)"
    }
  ],
  "experience": [
    {
      "company": "string",
      "title": "string",
      "duration": "string (e.g. Jun 2021 – Aug 2021)",
      "is_internship": true/false,
      "description": "string (1–2 sentence summary)"
    }
  ],
  "skills": ["list", "of", "skills"],
  "publications": ["list of publication titles (omit venue/authors)"]
}
"""

def _call_claude(text: str, api_key: str) -> dict:
    """Send CV text to Gemini and return parsed JSON dict."""
    from google import genai

    client = genai.Client(api_key=api_key)

    truncated = text[:24_000]
    prompt = (
        SYSTEM_PROMPT
        + "\n\nExtract structured career data from this CV text:\n\n"
        + truncated
    )

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            raw_text = response.text.strip()
            raw_text = re.sub(r"^```[a-z]*\n?", "", raw_text)
            raw_text = re.sub(r"\n?```$", "", raw_text.strip())
            return json.loads(raw_text)
        except json.JSONDecodeError as exc:
            log.warning(f"JSON decode error (attempt {attempt+1}): {exc}")
        except Exception as exc:
            log.warning(f"Gemini error (attempt {attempt+1}): {exc}")
        time.sleep(5)

    return {}
# ── Main parse function ───────────────────────────────────────────────────────

def parse_cv(
    source: CVSource,
    api_key: str,
    matched_company: str = "",
    matched_keyword: str = "",
) -> ParsedCV:
    """
    Extract text from a downloaded CV file, send to Claude, return ParsedCV.
    """
    log.debug(f"Parsing {source.raw_path} ({source.file_type})")

    text = extract_text(source)
    if not text.strip():
        return ParsedCV(
            user_login=source.user_login,
            source_url=source.url,
            parse_error="Could not extract text",
            matched_company=matched_company,
            matched_keyword=matched_keyword,
        )

    snippet = text[:500].replace("\n", " ")

    if not api_key:
        # No API key — return partial record with raw text only
        log.warning("ANTHROPIC_API_KEY not set — skipping Claude parse.")
        return ParsedCV(
            user_login=source.user_login,
            source_url=source.url,
            raw_text_snippet=snippet,
            parse_error="No ANTHROPIC_API_KEY — text extracted but not structured",
            matched_company=matched_company,
            matched_keyword=matched_keyword,
        )

    structured = _call_claude(text, api_key)
    if not structured:
        return ParsedCV(
            user_login=source.user_login,
            source_url=source.url,
            raw_text_snippet=snippet,
            parse_error="Claude returned empty / unparseable response",
            matched_company=matched_company,
            matched_keyword=matched_keyword,
        )

    education = [
        Education(
            school=e.get("school", ""),
            degree=e.get("degree", ""),
            field=e.get("field", ""),
            years=e.get("years", ""),
        )
        for e in structured.get("education", [])
    ]

    experience = [
        Experience(
            company=x.get("company", ""),
            title=x.get("title", ""),
            duration=x.get("duration", ""),
            is_internship=bool(x.get("is_internship", False)),
            description=x.get("description", ""),
        )
        for x in structured.get("experience", [])
    ]

    return ParsedCV(
        user_login=source.user_login,
        source_url=source.url,
        name=structured.get("name", ""),
        email=structured.get("email", ""),
        github=structured.get("github", ""),
        website=structured.get("website", ""),
        summary=structured.get("summary", ""),
        education=education,
        experience=experience,
        skills=structured.get("skills", []),
        publications=structured.get("publications", []),
        raw_text_snippet=snippet,
        matched_company=matched_company,
        matched_keyword=matched_keyword,
    )
