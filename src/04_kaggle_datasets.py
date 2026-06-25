"""
Script 4: Kaggle Job Postings Dataset Downloader
=================================================
Downloads job posting and salary datasets from Kaggle.

Install: pip install kaggle pandas
Setup:   kaggle.json must be at ~/.kaggle/ or ~/.config/kaggle/
Run:     python src/04_kaggle_datasets.py
Output:  data/raw/kaggle_jobs/
"""

import os
import sys
import shutil
import subprocess
import pandas as pd
from pathlib import Path

OUTPUT_DIR = Path("data/raw/kaggle_jobs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Verified working Kaggle dataset slugs ──────────────────────────────────────
DATASETS = {
    # LinkedIn 1.3M jobs with skills — verified slug
    "linkedin_job_postings": {
        "slug": "asaniczka/1-3m-linkedin-jobs-and-skills-2024",
        "size": "large",   # >500MB — will take a while
        "desc": "1.3M LinkedIn job postings with skills (2024)",
    },
    # Data Analyst jobs — already worked
    "data_analyst_jobs": {
        "slug": "andrewmvd/data-analyst-jobs",
        "size": "small",
        "desc": "Data Analyst job postings with salary & skills",
    },
    # Data Science job postings 2024 — corrected slug
    "ds_job_postings": {
        "slug": "asaniczka/data-science-job-postings-and-skills",
        "size": "medium",
        "desc": "Data Science job postings and skills (2024)",
    },
    # AI job market insights
    "ai_job_market": {
        "slug": "uom190346a/ai-powered-job-market-insights",
        "size": "small",
        "desc": "AI-powered job market insights dataset",
    },
    # Data Science salaries 2020–2024 — corrected slug
    "ds_salaries": {
        "slug": "sazidthe1/data-science-salaries",
        "size": "small",
        "desc": "Data Science salaries 2020–2024",
    },
    # Jobs and salaries in data field 2024
    "data_jobs_salaries_2024": {
        "slug": "murilozangari/jobs-and-salaries-in-data-field-2024",
        "size": "small",
        "desc": "Jobs and salaries in data field 2024",
    },
}

# Timeout per size category (seconds)
TIMEOUTS = {"small": 300, "medium": 900, "large": 1800}


def get_kaggle_cmd():
    """Find kaggle CLI regardless of install method."""
    if shutil.which("kaggle"):
        return ["kaggle"]
    home = os.path.expanduser("~")
    for path in [
        os.path.join(home, ".local/bin/kaggle"),
        "/usr/local/bin/kaggle",
    ]:
        if os.path.isfile(path):
            return [path]
    # fallback to python -m kaggle
    return [sys.executable, "-m", "kaggle"]


def download_dataset(name, slug, size):
    dest    = OUTPUT_DIR / name
    dest.mkdir(exist_ok=True)
    timeout = TIMEOUTS.get(size, 600)

    print(f"\n  Slug:    kaggle.com/datasets/{slug}")
    print(f"  Size:    {size} (timeout: {timeout//60} min)")

    cmd = get_kaggle_cmd() + [
        "datasets", "download",
        "--dataset", slug,
        "--path",    str(dest),
        "--unzip",
        "--quiet",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

        if result.returncode != 0:
            err = result.stderr.strip()
            if "404" in err or "not found" in err.lower():
                print(f"  [404] Dataset not found — slug may have changed")
            elif "403" in err or "forbidden" in err.lower():
                print(f"  [403] Access denied — dataset may require accepting terms on Kaggle website")
                print(f"        Visit: https://www.kaggle.com/datasets/{slug}")
            elif not err:
                print(f"  [ERROR] Failed with no error message (possibly network issue)")
            else:
                print(f"  [ERROR] {err[:200]}")
            return False

        files = list(dest.glob("**/*.csv")) + list(dest.glob("**/*.xlsx"))
        if not files:
            print(f"  [WARN] Downloaded but no CSV/XLSX found")
            return False

        total_mb = sum(f.stat().st_size for f in files) / 1e6
        print(f"  ✓ {len(files)} file(s), {total_mb:.1f} MB total:")
        for f in files[:3]:   # show max 3
            print(f"    {f.name} ({f.stat().st_size/1e6:.1f} MB)")
        if len(files) > 3:
            print(f"    ... and {len(files)-3} more")
        return True

    except subprocess.TimeoutExpired:
        print(f"  [TIMEOUT] Exceeded {timeout//60} min limit")
        print(f"  Manual download: https://www.kaggle.com/datasets/{slug}")
        print(f"  Save ZIP to: {dest}/ then unzip there")
        return False
    except Exception as e:
        print(f"  [ERROR] {type(e).__name__}: {e}")
        return False


def preview(name):
    dest  = OUTPUT_DIR / name
    files = list(dest.glob("**/*.csv"))
    if not files:
        return
    # preview the largest CSV
    f = max(files, key=lambda x: x.stat().st_size)
    try:
        df = pd.read_csv(f, nrows=3, low_memory=False)
        print(f"  Columns: {list(df.columns[:8])}{'...' if len(df.columns)>8 else ''}")
    except Exception:
        pass


def main():
    print("=" * 55)
    print("  Kaggle Job Data Downloader — AI Shift Project")
    print("=" * 55)

    # Check credentials
    home = Path.home()
    cred = home/".kaggle"/"kaggle.json"
    if not cred.exists():
        cred = home/".config"/"kaggle"/"kaggle.json"
    if not cred.exists():
        print("[ERROR] kaggle.json not found. Run: kaggle setup")
        return

    succeeded, failed = [], []

    for name, info in DATASETS.items():
        print(f"\n{'─'*45}")
        print(f"  [{name}]  {info['desc']}")
        ok = download_dataset(name, info["slug"], info["size"])
        if ok:
            preview(name)
            succeeded.append(name)
        else:
            failed.append((name, info["slug"]))

    # Summary
    print(f"\n{'='*55}")
    print(f"  Downloaded: {len(succeeded)}/{len(DATASETS)}")

    if succeeded:
        print(f"\n  ✓ Success:")
        for n in succeeded:
            print(f"    - {n}")

    if failed:
        print(f"\n  ✗ Failed ({len(failed)}) — manual download links:")
        for name, slug in failed:
            print(f"    - {name}")
            print(f"      https://www.kaggle.com/datasets/{slug}")
        print(f"\n  For manual downloads: save the ZIP into")
        print(f"  data/raw/kaggle_jobs/<dataset_name>/ and unzip there.")

    print(f"\n  Data saved → data/raw/kaggle_jobs/")
    print("  Done.")


if __name__ == "__main__":
    main()
