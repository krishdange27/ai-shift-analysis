"""
Script 3: Stack Overflow Developer Survey Downloader
======================================================
Downloads surveys via Kaggle CLI (fast, compressed, reliable).
Falls back to direct GitHub CSV if a year isn't on Kaggle.

Install: pip install kaggle pandas requests
Run:     python src/03_stackoverflow_survey.py
Output:  data/raw/stackoverflow/
"""

import sys
import time
import subprocess
import shutil
import requests
import pandas as pd
from pathlib import Path
from io import StringIO

OUTPUT_DIR = Path("data/raw/stackoverflow")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Config ─────────────────────────────────────────────────────────────────────

# Kaggle dataset slugs — official Stack Overflow account
# If a slug 404s, the fallback GitHub URL is tried automatically
YEARS = {
    2020: {
        "kaggle": "stackoverflow/stack-overflow-2020-developer-survey",
        "github": "https://github.com/StackExchange/Survey/raw/refs/heads/main/packages/archive/2020/results.csv",
    },
    2021: {
        "kaggle": "stackoverflow/stack-overflow-2021-developer-survey",
        "github": "https://github.com/StackExchange/Survey/raw/refs/heads/main/packages/archive/2021/results.csv",
    },
    2022: {
        "kaggle": "stackoverflow/stack-overflow-2022-developer-survey",
        "github": "https://github.com/StackExchange/Survey/raw/refs/heads/main/packages/archive/2022/results.csv",
    },
    2023: {
        "kaggle": "stackoverflow/stack-overflow-2023-developer-survey",
        "github": "https://github.com/StackExchange/Survey/raw/refs/heads/main/packages/archive/2023/results.csv",
    },
    2024: {
        "kaggle": "stackoverflow/stack-overflow-2024-developer-survey",
        "github": "https://github.com/StackExchange/Survey/raw/refs/heads/main/packages/archive/2024/results.csv",
    },
    2025: {
        "kaggle": "stackoverflow/stack-overflow-2025-developer-survey",
        "github": "https://github.com/StackExchange/Survey/raw/refs/heads/main/packages/archive/2025/results.csv",
    },
}

COLUMNS_OF_INTEREST = [
    "ResponseId", "MainBranch", "Employment", "Country", "EdLevel",
    "YearsCode", "YearsCodePro", "DevType",
    "LanguageHaveWorkedWith", "LanguageWantToWorkWith",
    "DatabaseHaveWorkedWith", "MiscTechHaveWorkedWith",
    "ToolsTechHaveWorkedWith", "ToolsTechWantToWorkWith",
    "AISearchHaveWorkedWith", "AISearchWantToWorkWith",
    "AIDevHaveWorkedWith", "AIDevWantToWorkWith",
    "AIAcc", "AIBen", "AIThreat", "AISelect",
    "Currency", "CompTotal", "ConvertedCompYearly",
    "JobSat",
]

# ── Strategy A: Kaggle CLI ─────────────────────────────────────────────────────

def download_via_kaggle(year, slug):
    """Download and unzip via kaggle CLI. Returns path to CSV or None."""
    year_dir = OUTPUT_DIR / str(year)
    year_dir.mkdir(exist_ok=True)

    print(f"  [Kaggle] Downloading: {slug}")
    cmd = [
        sys.executable, "-m", "kaggle",
        "datasets", "download",
        "--dataset", slug,
        "--path", str(year_dir),
        "--unzip",
        "--quiet",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            err = result.stderr.strip()
            if "404" in err or "not found" in err.lower():
                print(f"  [Kaggle] 404 — dataset slug may have changed.")
            else:
                print(f"  [Kaggle] Failed: {err[:200]}")
            return None

        # Find the main survey CSV (skip schema files)
        csvs = [f for f in year_dir.glob("**/*.csv")
                if "schema" not in f.name.lower()
                and "readme" not in f.name.lower()]

        if not csvs:
            print(f"  [Kaggle] No CSV found after download.")
            return None

        # Pick largest CSV (that's the responses file)
        main_csv = max(csvs, key=lambda f: f.stat().st_size)
        print(f"  [Kaggle] ✓ Got: {main_csv.name} ({main_csv.stat().st_size/1e6:.1f} MB)")
        return main_csv

    except subprocess.TimeoutExpired:
        print(f"  [Kaggle] Timeout after 5 minutes.")
        return None
    except Exception as e:
        print(f"  [Kaggle] Error: {e}")
        return None


# ── Strategy B: GitHub direct CSV ─────────────────────────────────────────────

def download_via_github(year, url):
    """Download CSV directly from GitHub with a generous timeout."""
    print(f"  [GitHub] Trying: {url}")
    headers = {"User-Agent": "Mozilla/5.0 (research/public-data)"}
    try:
        # Stream with long timeout — GitHub CSVs can be 50–100MB
        resp = requests.get(url, headers=headers, timeout=(10, 180), stream=True)
        resp.raise_for_status()

        size = int(resp.headers.get("Content-Length", 0))
        if size:
            print(f"  [GitHub] File size: {size/1e6:.1f} MB — downloading...")

        content = b""
        downloaded = 0
        for chunk in resp.iter_content(chunk_size=1024*1024):
            content += chunk
            downloaded += len(chunk)
            if downloaded % (10*1024*1024) < 1024*1024:
                print(f"  [GitHub] {downloaded/1e6:.0f} MB downloaded...")

        # Save raw file
        year_dir = OUTPUT_DIR / str(year)
        year_dir.mkdir(exist_ok=True)
        raw_path = year_dir / f"survey_{year}_raw.csv"
        raw_path.write_bytes(content)
        print(f"  [GitHub] ✓ Saved {downloaded/1e6:.1f} MB → {raw_path.name}")
        return raw_path

    except requests.exceptions.Timeout:
        print(f"  [GitHub] Timed out. Your connection may be too slow for this file.")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"  [GitHub] HTTP {e.response.status_code} — URL may have changed.")
        return None
    except Exception as e:
        print(f"  [GitHub] Error: {type(e).__name__}: {e}")
        return None


# ── Process + Filter ───────────────────────────────────────────────────────────

def process_survey_csv(csv_path, year):
    """Read CSV, filter columns, add year, return DataFrame."""
    try:
        df = pd.read_csv(csv_path, low_memory=False)
        print(f"  Shape: {df.shape[0]:,} rows × {df.shape[1]} columns")

        keep    = [c for c in COLUMNS_OF_INTEREST if c in df.columns]
        missing = [c for c in COLUMNS_OF_INTEREST if c not in df.columns]
        df      = df[keep].copy()
        df["survey_year"] = year

        if missing:
            print(f"  Columns not in {year}: {missing[:5]}{'...' if len(missing)>5 else ''}")

        return df
    except Exception as e:
        print(f"  [ERROR] Could not read CSV: {e}")
        return None


def extract_ai_adoption(df, year):
    """Count AI tool mentions from semicolon-separated multi-select columns."""
    ai_cols = [c for c in df.columns if "AI" in c and df[c].dtype == object]
    rows = []
    for col in ai_cols:
        counts = (
            df[col].dropna()
            .str.split(";").explode().str.strip()
            .value_counts().reset_index()
        )
        counts.columns = ["tool", "count"]
        counts["column"] = col
        counts["year"]   = year
        rows.append(counts)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  Stack Overflow Survey — AI Shift Project")
    print("=" * 55)
    print("  Strategy: Kaggle CLI first → GitHub fallback\n")

    all_dfs      = []
    ai_summaries = []
    results      = {}   # year → "kaggle" | "github" | "failed"

    for year, sources in YEARS.items():
        print(f"\n{'─'*45}")
        print(f"  [{year}]")

        csv_path = None

        # Try Kaggle first (fast, compressed)
        csv_path = download_via_kaggle(year, sources["kaggle"])

        # If Kaggle failed, try GitHub (slower, direct)
        if csv_path is None:
            print(f"  Kaggle failed — trying GitHub fallback...")
            csv_path = download_via_github(year, sources["github"])
            if csv_path:
                results[year] = "github"
        else:
            results[year] = "kaggle"

        if csv_path is None:
            print(f"  [SKIP] {year} — both sources failed.")
            results[year] = "failed"
            time.sleep(2)
            continue

        # Process and save clean filtered CSV
        df = process_survey_csv(csv_path, year)
        if df is None:
            results[year] = "failed"
            continue

        out = OUTPUT_DIR / f"survey_{year}.csv"
        df.to_csv(out, index=False)
        print(f"  ✓ Saved {len(df):,} rows → {out.name}")

        # AI adoption summary
        ai = extract_ai_adoption(df, year)
        if not ai.empty:
            ai.to_csv(OUTPUT_DIR / f"ai_adoption_{year}.csv", index=False)
            ai_summaries.append(ai)

        all_dfs.append(df)
        time.sleep(1)

    # ── Combine all years ──────────────────────────────────────────────────────
    print(f"\n{'─'*45}")
    if all_dfs:
        shared = set.intersection(*[set(d.columns) for d in all_dfs])
        combined = pd.concat([d[list(shared)] for d in all_dfs], ignore_index=True)
        combined.to_csv(OUTPUT_DIR / "survey_all_years_combined.csv", index=False)
        print(f"✓ Combined ({len(combined):,} rows) → survey_all_years_combined.csv")

    if ai_summaries:
        pd.concat(ai_summaries, ignore_index=True).to_csv(
            OUTPUT_DIR / "ai_adoption_all_years.csv", index=False
        )
        print(f"✓ AI adoption trends → ai_adoption_all_years.csv")

    # ── Summary ────────────────────────────────────────────────────────────────
    print(f"\n{'='*55}")
    print("  RESULTS")
    print(f"{'='*55}")
    for year, status in results.items():
        icon = "✓" if status != "failed" else "✗"
        print(f"  {icon} {year}  [{status}]")

    failed = [y for y, s in results.items() if s == "failed"]
    if failed:
        print(f"\n  Failed years: {failed}")
        print("  Manual fix: search on Kaggle for the correct dataset slug:")
        for y in failed:
            print(f"    kaggle.com/datasets?search=stack+overflow+{y}+developer+survey")

    print("\nDone.")


if __name__ == "__main__":
    main()
