INFO:
A career-research tool that discovers public CVs and resumes from robotics engineers on GitHub and personal websites and aggregates it into actionable insights about what backgrounds lead to roles at top robotics companies.

INSTALLATION
```bash
git clone https://github.com/ryan-shin14/robotics_cvscraper
cd robotics-cv-scraper
pip install -r requirements.txt
```


CONFIGURATION
```bash
cp .env.example .env
# Edit .env and fill in GITHUB_TOKEN (required) and ANTHROPIC_API_KEY (optional)
export $(grep -v '^#' .env | xargs)
```

**GitHub Token** — create a free Personal Access Token at https://github.com/settings/tokens  
Scopes needed: `read:user` only. No write permissions.

**Anthropic API Key** — get one at https://console.anthropic.com/  
Optional: without it the tool still downloads and extracts raw text, just without structured parsing.

---

## Usage

Run the full pipeline end-to-end:
```bash
python src/main.py --all
```

Or run steps individually:
```bash
# Step 1: Find GitHub users at target companies
python src/main.py --discover

# Step 2: Download their CV files
python src/main.py --fetch

# Step 3: Parse CVs into structured data (needs ANTHROPIC_API_KEY)
python src/main.py --parse

# Step 4: Generate career-path analysis report
python src/main.py --analyse
```

Each step caches its output, so you can re-run individual steps without repeating earlier work.

---

## Output

```
data/
  raw/
    <github_login>/        # Downloaded raw CV files (PDF/HTML)
    _users.json            # Discovered GitHub users
    _sources.json          # All found CV file URLs
  parsed/
    <login>_<slug>.json    # Structured ParsedCV for each CV
    analysis_report.json   # Aggregated career-path report
logs/
  scraper.log              # Full debug log
```

### Example parsed CV (`data/parsed/jdoe_resume.json`)
```json
{
  "user_login": "jdoe",
  "name": "Jane Doe",
  "education": [
    { "school": "MIT", "degree": "MS", "field": "Robotics", "years": "2019–2021" }
  ],
  "experience": [
    {
      "company": "Boston Dynamics",
      "title": "Software Engineer",
      "duration": "Jul 2021–present",
      "is_internship": false,
      "description": "Motion planning for Spot quadruped."
    }
  ],
  "skills": ["ROS2", "C++", "Python", "MuJoCo", "PyTorch"],
  "matched_company": "Boston Dynamics",
  "matched_keyword": "robotics"
}
```

### Analysis report highlights
- Top universities feeding into each company
- Degree level distribution (BS / MS / PhD)
- Most common skills by company
- Internship-to-full-time pipeline patterns
- Ranked list of all employers that appear in CVs

---

## Customising targets

Edit `src/config.py`:

```python
TARGET_COMPANIES = [
    "Boston Dynamics",
    "Figure AI",
    # Add or remove companies here
]

ROLE_KEYWORDS = [
    "robotics",
    "controls engineer",
    # Add domain keywords here
]
```

---

## Project structure

```
src/
  config.py           — All tunable settings in one place
  logger.py           — Shared logging setup
  models.py           — Data classes (GitHubUser, CVSource, ParsedCV, …)
  github_discovery.py — GitHub API user search
  cv_fetcher.py       — CV file discovery & download
  cv_parser.py        — Text extraction + Claude structured parsing
  analysis.py         — Aggregation & report generation
  main.py             — CLI orchestrator
```

---

## Rate limits & etiquette

| API | Limit | How we handle it |
|-----|-------|-----------------|
| GitHub Search | 30 req/min (auth) | 2.5s delay between calls |
| GitHub Core | 5 000 req/hr (auth) | Minimal repo lookups |
| Personal sites | No formal limit | 1.5s delay, descriptive User-Agent |
| Claude API | Depends on tier | 1s delay, 3 retries with back-off |

The bot identifies itself with:  
`User-Agent: robotics-career-research-bot/1.0 (public CV data only; contact: see repo)`

---

## Limitations

- Finds engineers who (a) have GitHub accounts and (b) have posted CVs publicly — a subset of all engineers
- GitHub bio search is fuzzy; expect some false positives
- CV parsing quality depends on PDF formatting (text-layer PDFs parse well; scanned PDFs may not)
- Claude extraction may miss non-standard CV formats

---

## License

MIT
