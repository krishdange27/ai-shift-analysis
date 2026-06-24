"""
Script 2: BLS Employment Data Collector
========================================
BLS blocks all automated downloads (API returns empty, FTP returns 403).
Solution: Use Kaggle — same official BLS/OEWS data, pre-packaged, no blocks.

Datasets used:
  - gauravduttakiit/occupational-employment-wage-stats  (OEWS 2019–2024)
  - asaniczka/jobs-on-the-rise-2024-linkedin           (LinkedIn job trends)
  - jpmiller/public-sector-employment                  (broader employment)

Install: pip install kaggle pandas openpyxl
Run:     python src/02_bls_employment.py
Output:  data/raw/bls/
"""

import sys
import subprocess
import pandas as pd
from pathlib import Path

import shutil as _shutil

def _get_kaggle_cmd():
    """Find kaggle executable regardless of how it was installed."""
    import subprocess, sys, os
    # Try direct CLI first
    if _shutil.which("kaggle"):
        return ["kaggle"]
    # Try common user install paths
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, ".local/bin/kaggle"),
        os.path.join(home, "/.local/bin/kaggle"),
        "/usr/local/bin/kaggle",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return [c]
    # Last resort: python -m kaggle with the user's pip python
    pip_python = _shutil.which("python3") or _shutil.which("python") or sys.executable
    return [pip_python, "-m", "kaggle"]


OUTPUT_DIR = Path("data/raw/bls")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Kaggle datasets containing BLS/OEWS employment data ───────────────────────
DATASETS = {
    "oews_employment_wages": {
        "slug":   "gauravduttakiit/occupational-employment-wage-stats",
        "desc":   "BLS OEWS national employment & wages by occupation 2019–2024",
    },
    "us_tech_employment": {
        "slug":   "jpmiller/public-sector-employment",
        "desc":   "US employment data by sector and occupation",
    },
    "ai_job_market": {
        "slug":   "uom190346a/ai-jobs-in-2024",
        "desc":   "AI/ML specific job market data 2024",
    },
    "data_science_salaries": {
        "slug":   "hummaamqasim/data-science-jobs-and-salaries",
        "desc":   "Data science & AI role salaries 2020–2024",
    },
    "tech_employment_trends": {
        "slug":   "ruchi798/data-science-job-salaries",
        "desc":   "Tech job salaries and employment by role 2020–2023",
    },
}

# SOC occupation codes we care about — used to filter OEWS data
TARGET_OCCUPATIONS = {
    "15-1132": "Software Developers",
    "15-2051": "Data Scientists",
    "15-1221": "Computer and Information Research Scientists",
    "15-1211": "Computer Systems Analysts",
    "15-1243": "Database Architects",
    "15-1299": "Computer Occupations NEC",
    "15-1200": "Computer Occupations (all)",
    "15-1252": "Software Quality Assurance Analysts",
    "15-2031": "Operations Research Analysts",
}


def download_kaggle(name, slug, out_dir):
    """Download and unzip a Kaggle dataset."""
    dest = out_dir / name
    dest.mkdir(exist_ok=True)

    print(f"\n  [{name}] kaggle.com/datasets/{slug}")
    cmd = [
        "kaggle", "datasets", "download",
        "--dataset", slug,
        "--path",    str(dest),
        "--unzip", "--quiet",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            err = result.stderr.strip()
            if "404" in err or "not found" in err.lower():
                print(f"  [404] Slug changed. Search: kaggle.com/datasets?search={name}")
            else:
                print(f"  [FAIL] {err[:150]}")
            return []

        csvs = list(dest.glob("**/*.csv"))
        xlsxs = list(dest.glob("**/*.xlsx"))
        files = csvs + xlsxs
        if files:
            for f in files:
                print(f"  ✓ {f.name} ({f.stat().st_size/1e6:.1f} MB)")
        else:
            print(f"  [WARN] No CSV/XLSX found after download")
        return files

    except subprocess.TimeoutExpired:
        print(f"  [TIMEOUT] Took >5 min — try again or download manually")
        return []
    except Exception as e:
        print(f"  [ERROR] {e}")
        return []


def filter_oews(files, out_dir):
    """
    Filter OEWS dataset to only tech/AI occupations and save clean CSVs.
    OEWS files have columns: OCC_CODE, OCC_TITLE, TOT_EMP, A_MEAN, A_MEDIAN etc.
    """
    oews_files = [f for f in files if "oew" in f.name.lower() or "occupation" in f.name.lower()
                  or "oes" in f.name.lower() or "national" in f.name.lower()]

    if not oews_files:
        oews_files = files  # try all of them

    all_filtered = []
    for fpath in oews_files:
        try:
            df = pd.read_csv(fpath, low_memory=False) if fpath.suffix == ".csv" \
                 else pd.read_excel(fpath)

            # Normalise column names
            df.columns = df.columns.str.strip().str.upper()

            # Find occupation code column
            occ_col = next((c for c in df.columns if "OCC_CODE" in c or "SOC" in c), None)
            if occ_col is None:
                continue

            # Filter for target occupations
            mask = df[occ_col].astype(str).str[:7].isin(TARGET_OCCUPATIONS.keys())
            subset = df[mask].copy()

            if subset.empty:
                continue

            subset["occupation_label"] = subset[occ_col].astype(str).str[:7].map(TARGET_OCCUPATIONS)
            subset["source_file"] = fpath.name
            all_filtered.append(subset)
            print(f"  Filtered {len(subset)} tech occupation rows from {fpath.name}")

        except Exception as e:
            print(f"  [SKIP] {fpath.name}: {e}")
            continue

    if all_filtered:
        combined = pd.concat(all_filtered, ignore_index=True)
        out = out_dir / "bls_oews_tech_occupations.csv"
        combined.to_csv(out, index=False)
        print(f"\n  ✓ Tech occupations filtered → {out.name}  ({len(combined)} rows)")
        return combined

    return pd.DataFrame()


def build_trend_summary(out_dir):
    """
    Combine salary/employment files across years into a trend table.
    Works across different dataset schemas by looking for common columns.
    """
    all_files = list(out_dir.glob("**/*.csv"))
    year_dfs  = []

    for fpath in all_files:
        if "trend" in fpath.name or "summary" in fpath.name or "bls_oews" in fpath.name:
            continue
        try:
            df = pd.read_csv(fpath, low_memory=False)
            df.columns = df.columns.str.strip().str.lower()

            # Look for year column
            year_col = next((c for c in df.columns if c in ("year","work_year","survey_year")), None)
            # Look for salary/wage column
            sal_col  = next((c for c in df.columns
                             if any(x in c for x in ("salary","wage","comp","pay"))), None)
            # Look for job title
            title_col = next((c for c in df.columns
                               if any(x in c for x in ("title","role","job_title","position","occ_title"))), None)

            if year_col and sal_col and title_col:
                subset = df[[year_col, title_col, sal_col]].dropna().copy()
                subset.columns = ["year", "job_title", "salary_usd"]
                subset["source"] = fpath.parent.name
                year_dfs.append(subset)

        except Exception:
            continue

    if year_dfs:
        trend = pd.concat(year_dfs, ignore_index=True)
        trend["year"]       = pd.to_numeric(trend["year"], errors="coerce")
        trend["salary_usd"] = pd.to_numeric(
            trend["salary_usd"].astype(str).str.replace(r"[,$]","",regex=True),
            errors="coerce"
        )
        trend = trend.dropna(subset=["year","salary_usd"])
        trend = trend[trend["year"].between(2018, 2026)]

        out = out_dir / "bls_salary_trends_combined.csv"
        trend.to_csv(out, index=False)
        print(f"\n  ✓ Salary trends combined → {out.name}  ({len(trend):,} rows, {trend['year'].nunique()} years)")

        # Year-over-year summary
        yoy = trend.groupby(["year","job_title"])["salary_usd"].agg(["mean","median","count"]).reset_index()
        yoy.columns = ["year","job_title","mean_salary","median_salary","count"]
        yoy.to_csv(out_dir / "bls_salary_yoy_summary.csv", index=False)
        print(f"  ✓ Year-over-year summary → bls_salary_yoy_summary.csv")

        return trend

    return pd.DataFrame()


def main():
    print("=" * 55)
    print("  BLS Employment Data Collector — AI Shift Project")
    print("=" * 55)
    print("  Source: Kaggle (BLS blocks direct automation)")
    print("  Data:   OEWS employment + tech role salary trends\n")

    all_files   = []
    succeeded   = []
    failed      = []

    for name, info in DATASETS.items():
        print(f"\n{'─'*45}")
        print(f"  {info['desc']}")
        files = download_kaggle(name, info["slug"], OUTPUT_DIR)
        if files:
            all_files.extend(files)
            succeeded.append(name)
        else:
            failed.append((name, info["slug"]))

    # Post-process
    print(f"\n{'─'*45}")
    print("  Processing downloaded files...\n")

    oews_files = [f for f in all_files if f.parent.name == "oews_employment_wages"]
    if oews_files:
        filter_oews(oews_files, OUTPUT_DIR)

    build_trend_summary(OUTPUT_DIR)

    # Summary
    print(f"\n{'='*55}")
    print(f"  Downloaded: {len(succeeded)}/{len(DATASETS)} datasets")
    if failed:
        print(f"\n  Failed ({len(failed)}) — try updated slugs:")
        for name, slug in failed:
            search = name.replace("_", "+")
            print(f"  - {name}")
            print(f"    Search: kaggle.com/datasets?search={search}")
    print(f"\n  Files saved → data/raw/bls/")
    print("  Done.")


if __name__ == "__main__":
    main()
