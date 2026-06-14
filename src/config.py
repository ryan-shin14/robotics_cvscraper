"""
Central config — edit this file to tune targets and behavior.
"""

from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT     = Path(__file__).parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_OUT = ROOT / "data" / "parsed"
LOG_DIR  = ROOT / "logs"

for _d in (DATA_RAW, DATA_OUT, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── GitHub search targets ──────────────────────────────────────────────────────
TARGET_COMPANIES = [
    "Boston Dynamics",
    "Figure AI",
    "Agility Robotics",
    "Tesla",
    "NVIDIA",
    "Apptronik",
    "1X Technologies",
    "Sanctuary AI",
]

# Keywords used when searching GitHub user bios
ROLE_KEYWORDS = [
    "robotics",
    "controls engineer",
    "embedded systems",
    "autonomy",
    "mechatronics",
    "robot software",
]

# ── Scraping behaviour ─────────────────────────────────────────────────────────
# Max GitHub users to inspect per (company, keyword) pair
MAX_USERS_PER_QUERY = 30

# Seconds to wait between GitHub API calls (free tier: 30 req/min authenticated)
GITHUB_DELAY = 2.5

# Seconds to wait between CV fetches
CV_FETCH_DELAY = 1.5

# Max size (bytes) for a CV download before we skip it
MAX_CV_BYTES = 10 * 1024 * 1024   # 10 MB

# ── Claude API (for CV parsing) ────────────────────────────────────────────────
CLAUDE_MODEL   = "claude-sonnet-4-6"
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MAX_TOKENS = 1500

# ── CV filename patterns to look for in repos / pages ─────────────────────────
CV_FILENAME_PATTERNS = [
    "cv", "resume", "curriculum_vitae", "curriculum-vitae",
]
CV_EXTENSIONS = [".pdf", ".html", ".htm"]

# Pages branch names to try
PAGES_BRANCHES = ["gh-pages", "main", "master"]
