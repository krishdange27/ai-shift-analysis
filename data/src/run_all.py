"""
RUN_ALL.py — Master Data Acquisition Runner
============================================
Runs all 5 data collection scripts in sequence.
Check each script's docstring for prerequisites.

Usage:
  python src/run_all.py              # run everything
  python src/run_all.py --skip fred  # skip specific scripts

Prerequisites summary:
  Script 1 (Google Trends):   pip install pytrends pandas
  Script 2 (BLS):             pip install requests pandas  +  free BLS API key
  Script 3 (Stack Overflow):  pip install requests pandas
  Script 4 (Kaggle):          pip install kaggle pandas    +  kaggle.json setup
  Script 5 (FRED):            pip install fredapi pandas   +  free FRED API key

Install all at once:
  pip install pytrends requests pandas kaggle fredapi
"""

import sys
import time
import argparse
import subprocess
from pathlib import Path

SCRIPTS = [
    ("01_google_trends",    "src/01_google_trends.py",   ["pytrends", "pandas"]),
    ("02_bls_employment",   "src/02_bls_employment.py",  ["requests", "pandas"]),
    ("03_stackoverflow",    "src/03_stackoverflow_survey.py", ["requests", "pandas"]),
    ("04_kaggle_jobs",      "src/04_kaggle_datasets.py", ["kaggle", "pandas"]),
    ("05_fred_data",        "src/05_fred_data.py",       ["requests", "pandas"]),
]


def check_imports(packages: list[str]) -> list[str]:
    """Return list of packages that are NOT installed."""
    missing = []
    for pkg in packages:
        try:
            __import__(pkg.replace("-", "_"))
        except ImportError:
            missing.append(pkg)
    return missing


def run_script(name: str, path: str) -> bool:
    print(f"\n{'='*55}")
    print(f"  Running: {name}")
    print(f"{'='*55}")

    start = time.time()
    result = subprocess.run([sys.executable, path], timeout=600)
    elapsed = time.time() - start

    if result.returncode == 0:
        print(f"\n[✓] {name} completed in {elapsed:.0f}s")
        return True
    else:
        print(f"\n[✗] {name} FAILED (exit code {result.returncode})")
        return False


def main():
    parser = argparse.ArgumentParser(description="Run all AI Shift data collectors")
    parser.add_argument("--skip", nargs="*", default=[], help="Script names to skip")
    parser.add_argument("--only", nargs="*", default=[], help="Only run these scripts")
    args = parser.parse_args()

    print("\n" + "="*55)
    print("  AI Shift Project — Data Acquisition Master Runner")
    print("="*55)

    # Dependency check
    print("\n[Pre-flight] Checking installed packages...")
    all_missing = set()
    for name, path, deps in SCRIPTS:
        missing = check_imports(deps)
        if missing:
            all_missing.update(missing)
            print(f"  [MISSING] {name}: {missing}")
        else:
            print(f"  [OK]      {name}")

    if all_missing:
        print(f"\n[ACTION NEEDED] Install missing packages:")
        print(f"  pip install {' '.join(all_missing)}")
        print("\nThen re-run this script.")
        sys.exit(1)

    print("\n[OK] All packages installed. Starting collection...\n")

    results = {}
    for name, path, deps in SCRIPTS:
        if args.only and name not in args.only:
            print(f"[SKIP] {name} (not in --only list)")
            continue
        if name in args.skip:
            print(f"[SKIP] {name} (in --skip list)")
            continue

        ok = run_script(name, path)
        results[name] = ok
        time.sleep(2)  # brief pause between scripts

    # Final summary
    print("\n" + "="*55)
    print("  SUMMARY")
    print("="*55)
    for name, ok in results.items():
        status = "✓ SUCCESS" if ok else "✗ FAILED"
        print(f"  {status}  {name}")

    total    = len(results)
    succeeded = sum(results.values())
    print(f"\n  {succeeded}/{total} scripts completed successfully.")

    if succeeded < total:
        print("\n  Check error messages above.")
        print("  Common fixes:")
        print("    - BLS / FRED: add your API key to the script")
        print("    - Kaggle: run kaggle setup (see script 04 header)")
        print("    - Rate limits: re-run failed scripts after a few minutes")

    print("\n  Data saved to: data/raw/")
    print("  Next step: run notebooks/ for cleaning & EDA")


if __name__ == "__main__":
    main()
