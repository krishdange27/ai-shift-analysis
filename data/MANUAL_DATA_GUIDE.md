# Manual Data Collection Guide
## AI Shift Project — Non-Automatable Sources

These 3 sources require a one-time manual download (total: ~20 minutes).
After downloading, the Python scripts in `src/` handle all extraction.

---

## 1. World Economic Forum — Future of Jobs Report

**Why it matters:** Contains structured tables on job growth, job decline,
and skill demand forecasts. The 2020, 2023, and 2025 editions bracket
your study period perfectly.

**Where to get it:**
```
https://www.weforum.org/publications/the-future-of-jobs-report-2025/
https://www.weforum.org/publications/the-future-of-jobs-report-2023/
https://www.weforum.org/publications/the-future-of-jobs-report-2020/
```

**Steps:**
1. Go to each URL above
2. Click "Download PDF" (free, no paywall — just email required on some)
3. Save to: `data/raw/manual_reports/wef_jobs_2020.pdf`
                `data/raw/manual_reports/wef_jobs_2023.pdf`
                `data/raw/manual_reports/wef_jobs_2025.pdf`

**What we extract:** Tables on pages listing top growing/declining jobs,
top skills in demand, AI adoption rates by industry.

---

## 2. McKinsey Global Institute — AI Reports

**Why it matters:** Has quantitative estimates on automation potential
by occupation and sector, used widely in labor market research.

**Where to get it:**
```
https://www.mckinsey.com/mgi/our-research/generative-ai-and-the-future-of-work-in-america
https://www.mckinsey.com/capabilities/quantumblack/our-insights/the-state-of-ai
```

**Steps:**
1. Open each link above
2. Click "Download" or "Read the report" PDF button
3. Save to: `data/raw/manual_reports/mckinsey_ai_work_2023.pdf`
                `data/raw/manual_reports/mckinsey_state_of_ai_2024.pdf`

**Note:** McKinsey requires a free account registration for some PDFs.
Takes 1 minute. No credit card.

**What we extract:** Stats on AI adoption rates, % tasks automatable
per job category, investment figures.

---

## 3. LinkedIn Economic Graph — Workforce Reports

**Why it matters:** LinkedIn publishes "Jobs on the Rise" and
"Skills on the Rise" data yearly — exactly what this project needs.

**Where to get it:**
```
https://economicgraph.linkedin.com/research
```

**Steps:**
1. Go to the URL above
2. Filter by: Workforce Reports / Future of Work
3. Download PDFs for 2022, 2023, 2024 editions
4. Save to: `data/raw/manual_reports/linkedin_workforce_2022.pdf`
                `data/raw/manual_reports/linkedin_workforce_2023.pdf`
                `data/raw/manual_reports/linkedin_workforce_2024.pdf`

**Bonus:** Some reports include downloadable Excel/CSV files with the
underlying data — grab those too if available. Save to `data/raw/kaggle_jobs/`.

---

## 4. Stack Overflow State of AI Survey (supplementary)

**Why it matters:** Separate from the Dev Survey — specifically about
AI usage patterns in software development.

**Where to get it:**
```
https://survey.stackoverflow.co/2024/ai
```

**Steps:**
1. Screenshot or PDF-print the key charts
2. Note the headline % numbers manually in a notes file
3. Save to: `data/raw/manual_reports/so_ai_survey_notes_2024.txt`

---

## After Manual Download

Once PDFs are in `data/raw/manual_reports/`, run this to extract tables:

```bash
pip install pdfplumber pandas
python src/06_extract_pdf_tables.py   # (we'll write this next)
```

---

## Folder structure after all collection

```
data/
├── raw/
│   ├── google_trends/         ← Script 01 (automated)
│   ├── bls/                   ← Script 02 (automated)
│   ├── stackoverflow/         ← Script 03 (automated)
│   ├── kaggle_jobs/           ← Script 04 (semi-automated)
│   ├── fred/                  ← Script 05 (automated)
│   └── manual_reports/        ← This guide (manual)
│       ├── wef_jobs_2023.pdf
│       ├── mckinsey_ai_work_2023.pdf
│       └── linkedin_workforce_2023.pdf
└── processed/                 ← Cleaned data (next phase)
```
