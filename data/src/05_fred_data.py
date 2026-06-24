"""
Script 5: FRED Economic Data Collector
========================================
Pulls macro employment and tech-sector data from the Federal Reserve
Economic Data (FRED) free public API.

Get your FREE key in 30 seconds:
  https://fred.stlouisfed.org/docs/api/api_key.html

Usage:
  python src/05_fred_data.py --key YOUR_KEY_HERE
  OR set it once in the script below (FRED_API_KEY = "...")

Install: pip install requests pandas
Output:  data/raw/fred/
"""

import time
import argparse
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────

OUTPUT_DIR = Path("data/raw/fred")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Set your key here permanently so you never need to pass --key again
FRED_API_KEY = "e4024c25d6747df6a4699fad9ac1f07e"

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
FRED_META  = "https://api.stlouisfed.org/fred/series"

START_DATE = "2018-01-01"
END_DATE   = datetime.today().strftime("%Y-%m-%d")

# ── Series ────────────────────────────────────────────────────────────────────

SERIES = {
    # Tech sector employment
    "info_sector_employment":        "USINFO",
    "software_publishers_emp":       "CES5051200001",
    "computer_systems_design_emp":   "CES6054150001",

    # Unemployment
    "unemployment_rate":             "UNRATE",
    "unemployment_bachelors_plus":   "LNS14027659",

    # Tech wages
    "info_sector_weekly_earnings":   "CES5500000030",

    # Job openings (JOLTS)
    "job_openings_total":            "JTSJOL",
    "job_openings_prof_services":    "JTS6000JOL",

    # Layoffs
    "layoffs_total":                 "JTSLDL",
    "layoffs_info_sector":           "JTU5100LDL",

    # Macro
    "real_gdp":                      "GDPC1",
    "labor_productivity":            "OPHNFB",
}

# ── Fetcher ───────────────────────────────────────────────────────────────────

def fetch_series(series_id, api_key):
    params = {
        "series_id": series_id, "api_key": api_key,
        "file_type": "json",
        "observation_start": START_DATE,
        "observation_end":   END_DATE,
    }
    try:
        r = requests.get(FRED_BASE, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        if "observations" not in data:
            print(f"  [WARN] No data: {data.get('error_message','')}")
            return None
        df = pd.DataFrame(data["observations"])[["date","value"]]
        df["date"]  = pd.to_datetime(df["date"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        return df
    except requests.exceptions.HTTPError as e:
        if "400" in str(e):
            print(f"  [ERROR] Bad series ID or invalid key")
        else:
            print(f"  [HTTP ERROR] {e}")
        return None
    except Exception as e:
        print(f"  [ERROR] {e}")
        return None


def fetch_meta(series_id, api_key):
    try:
        r = requests.get(FRED_META, params={"series_id": series_id, "api_key": api_key, "file_type": "json"}, timeout=10)
        s = r.json().get("seriess", [{}])[0]
        return s.get("title",""), s.get("units_short",""), s.get("frequency_short","")
    except Exception:
        return "", "", ""

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", default=None, help="Your FRED API key")
    args = parser.parse_args()

    api_key = args.key or FRED_API_KEY

    print("=" * 55)
    print("  FRED Economic Data Collector — AI Shift Project")
    print("=" * 55)

    if api_key == "YOUR_FRED_API_KEY_HERE":
        print("""
[ERROR] No FRED API key provided.

Get your FREE key in 30 seconds:
  1. Go to: https://fred.stlouisfed.org/docs/api/api_key.html
  2. Click 'Request API Key'
  3. Fill name + reason (e.g. 'student research project')
  4. Key arrives instantly in your email

Then run:
  python src/05_fred_data.py --key YOUR_KEY_HERE

Or paste it permanently into the script at line:
  FRED_API_KEY = "paste_here"
""")
        return

    all_dfs = []
    meta_rows = []
    failed  = []

    for label, series_id in SERIES.items():
        print(f"\n[{label}]")
        title, units, freq = fetch_meta(series_id, api_key)
        if title:
            print(f"  {title} | {units} | {freq}")

        df = fetch_series(series_id, api_key)
        if df is None:
            failed.append(label)
            continue

        df["series_id"] = series_id
        df["label"]     = label
        df["units"]     = units
        df["frequency"] = freq

        out = OUTPUT_DIR / f"{label}.csv"
        df.to_csv(out, index=False)
        print(f"  ✓ {len(df)} observations → {out.name}")

        all_dfs.append(df)
        meta_rows.append({"label": label, "series_id": series_id, "title": title, "units": units})
        time.sleep(0.3)

    if all_dfs:
        combined = pd.concat(all_dfs, ignore_index=True)
        combined.to_csv(OUTPUT_DIR / "fred_all_series_long.csv", index=False)

        wide = combined.pivot_table(index="date", columns="label", values="value").reset_index()
        wide.to_csv(OUTPUT_DIR / "fred_all_series_wide.csv", index=False)

        pd.DataFrame(meta_rows).to_csv(OUTPUT_DIR / "fred_series_metadata.csv", index=False)

        print(f"\n✓ Long  → fred_all_series_long.csv  ({len(combined):,} rows)")
        print(f"✓ Wide  → fred_all_series_wide.csv   {wide.shape}")
        print(f"✓ Meta  → fred_series_metadata.csv")

    if failed:
        print(f"\n[WARN] Failed: {failed}")

    print(f"\nSaved {len(all_dfs)}/{len(SERIES)} series. Done.")


if __name__ == "__main__":
    main()
