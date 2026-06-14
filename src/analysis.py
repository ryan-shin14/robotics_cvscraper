"""
Analysis
========
Reads all parsed CVs and produces a career-path summary:

- Most common undergraduate schools
- Most common degree fields
- Internship patterns (where people interned before landing full-time roles)
- Skill frequency
- Career trajectory lengths
- Top previous employers

Run standalone:  python analysis.py
Or import run_analysis() from main.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import DATA_OUT
from models import ParsedCV, Education, Experience
from logger import get_logger

log = get_logger("analysis")


def load_parsed_cvs() -> list[ParsedCV]:
    """Load all JSON files from data/parsed/ into ParsedCV objects."""
    cvs: list[ParsedCV] = []
    for path in DATA_OUT.glob("*.json"):
        try:
            raw = json.loads(path.read_text())
            edu = [Education(**e) for e in raw.pop("education", [])]
            exp = [Experience(**e) for e in raw.pop("experience", [])]
            cv  = ParsedCV(**raw)
            cv.education  = edu
            cv.experience = exp
            cvs.append(cv)
        except Exception as exc:
            log.warning(f"Could not load {path.name}: {exc}")
    return cvs


def analyse(cvs: list[ParsedCV]) -> dict:
    """
    Aggregate career-path signals across all parsed CVs.
    Returns a dict with human-readable summaries and ranked lists.
    """
    if not cvs:
        return {"error": "No parsed CVs found."}

    school_counter    = Counter()
    field_counter     = Counter()
    degree_counter    = Counter()
    skill_counter     = Counter()
    internship_counter= Counter()
    employer_counter  = Counter()
    years_to_full: list[int] = []

    for cv in cvs:
        # Education
        for edu in cv.education:
            if edu.school:
                school_counter[edu.school] += 1
            if edu.field:
                field_counter[edu.field] += 1
            if edu.degree:
                degree_counter[edu.degree.split()[0].upper()] += 1  # BS/MS/PhD

        # Skills
        for skill in cv.skills:
            skill_counter[skill.lower()] += 1

        # Experience
        internship_seen = False
        full_time_seen  = False
        for exp in cv.experience:
            if exp.company:
                employer_counter[exp.company] += 1
            if exp.is_internship and exp.company:
                internship_counter[exp.company] += 1
                internship_seen = True
            elif not exp.is_internship:
                full_time_seen = True

    # Companies with the most intern→fulltime pipelines
    # (simplistic: companies appearing in both internship and full-time roles)
    intern_set = set(internship_counter.keys())
    ft_employers = {
        c for cv in cvs
        for exp in cv.experience
        if not exp.is_internship and exp.company
        for c in [exp.company]
    }
    intern_pipeline = sorted(intern_set & ft_employers)

    # CVs with parse errors
    errored = [cv.user_login for cv in cvs if cv.parse_error]

    report = {
        "total_cvs_analysed": len(cvs),
        "cvs_with_parse_errors": len(errored),

        "top_schools": school_counter.most_common(20),
        "top_degree_fields": field_counter.most_common(15),
        "degree_levels": degree_counter.most_common(10),

        "top_skills": skill_counter.most_common(30),

        "top_internship_companies": internship_counter.most_common(15),
        "intern_to_fulltime_pipeline_companies": intern_pipeline,

        "all_employers_ranked": employer_counter.most_common(30),

        "by_target_company": _by_target_company(cvs),
    }
    return report


def _by_target_company(cvs: list[ParsedCV]) -> dict:
    """Break down key stats by the matched target company."""
    from collections import defaultdict
    groups: dict[str, list[ParsedCV]] = defaultdict(list)
    for cv in cvs:
        groups[cv.matched_company].append(cv)

    result = {}
    for company, group in groups.items():
        sc = Counter()
        sk = Counter()
        for cv in group:
            for edu in cv.education:
                if edu.school:
                    sc[edu.school] += 1
            for skill in cv.skills:
                sk[skill.lower()] += 1
        result[company] = {
            "count": len(group),
            "top_schools": sc.most_common(5),
            "top_skills": sk.most_common(10),
        }
    return result


def print_report(report: dict):
    """Pretty-print the analysis report to stdout."""
    def _section(title: str):
        print(f"\n{'═'*60}")
        print(f"  {title}")
        print(f"{'═'*60}")

    def _ranked(items: list[tuple], label: str = ""):
        for rank, (name, count) in enumerate(items, 1):
            print(f"  {rank:>3}. {name:<40} {count:>4}x")

    print(f"\n{'█'*60}")
    print(f"  Robotics CV Analysis — {report['total_cvs_analysed']} CVs")
    print(f"{'█'*60}")

    _section("Top Universities / Schools")
    _ranked(report["top_schools"])

    _section("Top Degree Fields")
    _ranked(report["top_degree_fields"])

    _section("Degree Levels (BS / MS / PhD)")
    _ranked(report["degree_levels"])

    _section("Top Skills")
    for rank, (skill, count) in enumerate(report["top_skills"], 1):
        print(f"  {rank:>3}. {skill:<40} {count:>4}x")

    _section("Top Internship Companies (feeder programs)")
    _ranked(report["top_internship_companies"])

    _section("Companies with Intern→Full-time Pipeline")
    for c in report["intern_to_fulltime_pipeline_companies"]:
        print(f"       {c}")

    _section("All Employers (ranked by appearances)")
    _ranked(report["all_employers_ranked"])

    _section("Per Target Company Breakdown")
    for company, stats in report["by_target_company"].items():
        print(f"\n  ▶  {company}  ({stats['count']} CVs)")
        print("     Schools:", ", ".join(s for s, _ in stats["top_schools"][:3]))
        print("     Skills: ", ", ".join(s for s, _ in stats["top_skills"][:5]))


if __name__ == "__main__":
    cvs    = load_parsed_cvs()
    report = analyse(cvs)
    print_report(report)

    out = DATA_OUT / "analysis_report.json"
    out.write_text(json.dumps(report, indent=2))
    log.info(f"Report saved → {out}")
