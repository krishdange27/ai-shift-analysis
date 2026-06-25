# =============================================================================
# src/clean_fred.py
# =============================================================================
# INPUT  : data/raw/fred/fred_all_series_wide.csv
# OUTPUT : data/processed/fred_clean.parquet
#
# CLEANING STEPS:
#   1. date → datetime
#   2. All numeric columns → float64
#   3. Quarterly series (real_gdp, labor_productivity) have NaN on
#      non-quarter months → forward fill (they don't change monthly)
#   4. Add YoY % change columns for employment series
#   5. Add covid_period flag (2020-03 to 2021-12)
#   6. Add pre/post ChatGPT flag
# =============================================================================

from __future__ import annotations
from pathlib import Path
import pandas as pd
import sys

sys.path.insert(0, str(Path(__file__).parent))
from utils_clean import (coerce_float, coerce_datetime,
                         add_date_flags, add_covid_flag, log_report, get_paths)

P = get_paths()

# Columns that are quarterly — need forward fill
QUARTERLY_COLS = ["real_gdp", "labor_productivity"]

# Employment series to compute YoY % change for
EMPLOYMENT_COLS = [
    "computer_systems_design_emp",
    "info_sector_employment",
    "software_publishers_emp",
    "unemployment_bachelors_plus",
    "unemployment_rate",
    "info_sector_weekly_earnings",
]


def clean_fred() -> pd.DataFrame:
    src = P["raw"] / "fred" / "fred_all_series_wide.csv"
    print(f"Reading {src} ...")
    df = pd.read_csv(src)
    rows_in = len(df)
    print(f"  Rows in: {rows_in}")

    # ── 1. Date ───────────────────────────────────────────────────────────────
    df["date"] = coerce_datetime(df["date"])
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    # ── 2. Numeric columns → float ────────────────────────────────────────────
    num_cols = [c for c in df.columns if c != "date"]
    for col in num_cols:
        df[col] = coerce_float(df[col])

    # ── 3. Forward-fill quarterly series ─────────────────────────────────────
    for col in QUARTERLY_COLS:
        if col in df.columns:
            before = df[col].isna().sum()
            df[col] = df[col].ffill()
            after  = df[col].isna().sum()
            print(f"  {col}: ffill filled {before - after} NaNs ({after} remain)")

    # ── 4. YoY % change for employment series ─────────────────────────────────
    # Shift 12 months back → (current - prior) / prior * 100
    for col in EMPLOYMENT_COLS:
        if col in df.columns:
            df[f"{col}_yoy_pct"] = (
                (df[col] - df[col].shift(12)) / df[col].shift(12) * 100
            ).round(3)

    # ── 5 & 6. Date flags ─────────────────────────────────────────────────────
    df = add_covid_flag(df, "date")
    df = add_date_flags(df, "date")

    # ── Save ──────────────────────────────────────────────────────────────────
    out = P["processed"] / "fred_clean.parquet"
    df.to_parquet(out, index=False)
    print(f"  Saved → {out}  ({len(df)} rows, {len(df.columns)} cols)")

    log_report({
        "source":   "fred",
        "rows_in":  rows_in,
        "rows_out": len(df),
        "notes": (
            f"Quarterly cols forward-filled: {QUARTERLY_COLS}. "
            f"YoY % change added for: {EMPLOYMENT_COLS}. "
            "covid_period flag: 2020-03 to 2021-12. "
            "pre/post_chatgpt flag added."
        ),
    }, P["report"])

    return df


if __name__ == "__main__":
    df = clean_fred()
    print(df.tail(5).to_string())
    print(f"\nDate range: {df['date'].min()} → {df['date'].max()}")
    print(f"COVID rows: {df['covid_period'].sum()}")
    yoy_cols = [c for c in df.columns if c.endswith("_yoy_pct")]
    print(f"YoY columns added: {yoy_cols}")
