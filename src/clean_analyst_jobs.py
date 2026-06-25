# =============================================================================
# src/clean_analyst_jobs.py
# =============================================================================
# INPUT  : data/raw/kaggle_jobs/data_analyst_jobs/DataAnalyst.csv
# OUTPUT : data/processed/analyst_jobs_clean.parquet
#
# CLEANING STEPS:
#   1. Drop unnamed index column
#   2. Salary Estimate → salary_min, salary_max, salary_mid (USD numeric)
#   3. Company Name has rating appended like "Vera Institute\n3.2" → split out
#   4. Founded: -1 → NaN
#   5. Size: string ranges → ordinal encoding + keep original
#   6. Rating → float, -1 → NaN
#   7. Competitors: -1 → NaN
#   8. Clean string columns (strip whitespace)
# =============================================================================

from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np
import sys

sys.path.insert(0, str(Path(__file__).parent))
from utils_clean import (coerce_float, coerce_int, clean_str,
                         parse_salary_range, log_report, get_paths)

P = get_paths()

# Ordinal mapping for company size
SIZE_ORDINAL = {
    "1 to 50 employees":       1,
    "51 to 200 employees":     2,
    "201 to 500 employees":    3,
    "501 to 1000 employees":   4,
    "1001 to 5000 employees":  5,
    "5001 to 10000 employees": 6,
    "10000+ employees":        7,
}


def clean_analyst_jobs() -> pd.DataFrame:
    src = P["raw"] / "kaggle_jobs" / "data_analyst_jobs" / "DataAnalyst.csv"
    print(f"Reading {src} ...")
    df = pd.read_csv(src)
    rows_in = len(df)
    print(f"  Rows in: {rows_in}")

    # ── 1. Drop unnamed index ─────────────────────────────────────────────────
    df = df.drop(columns=["Unnamed: 0"], errors="ignore")

    # ── 2. Salary parsing ─────────────────────────────────────────────────────
    sal = parse_salary_range(df["Salary Estimate"])
    df = pd.concat([df, sal], axis=1)
    df = df.drop(columns=["Salary Estimate"])
    print(f"  Salary mid range: ${df['salary_mid'].min():,.0f} – ${df['salary_mid'].max():,.0f}")

    # ── 3. Company Name — strip appended rating ───────────────────────────────
    # "Vera Institute of Justice\n3.2" → company_name="Vera Institute of Justice"
    df["company_name"] = (
        df["Company Name"]
        .astype(str)
        .str.split("\n").str[0]
        .str.strip()
        .replace({"nan": np.nan, "-1": np.nan})
    )
    df = df.drop(columns=["Company Name"])

    # ── 4. Rating: -1 → NaN ───────────────────────────────────────────────────
    df["Rating"] = coerce_float(df["Rating"])
    df.loc[df["Rating"] == -1, "Rating"] = np.nan
    df = df.rename(columns={"Rating": "company_rating"})

    # ── 5. Founded: -1 → NaN ──────────────────────────────────────────────────
    df["Founded"] = coerce_int(df["Founded"])
    df.loc[df["Founded"] == -1, "Founded"] = pd.NA
    df = df.rename(columns={"Founded": "founded_year"})

    # ── 6. Size — ordinal encoding ────────────────────────────────────────────
    df["size_label"] = clean_str(df["Size"])
    df["size_ordinal"] = (
        df["size_label"]
        .map(SIZE_ORDINAL)
        .astype("Int64")
    )
    df = df.drop(columns=["Size"])

    # ── 7. Competitors: -1 → NaN ──────────────────────────────────────────────
    df["Competitors"] = df["Competitors"].replace({"-1": np.nan, -1: np.nan})

    # ── 8. Clean string cols ──────────────────────────────────────────────────
    str_cols = ["Job Title", "Location", "Headquarters", "Type of ownership",
                "Industry", "Sector", "Revenue"]
    for col in str_cols:
        if col in df.columns:
            df[col] = clean_str(df[col])

    # ── Rename for consistency ────────────────────────────────────────────────
    df = df.rename(columns={
        "Job Title":          "job_title",
        "Job Description":    "job_description",
        "Location":           "location",
        "Headquarters":       "headquarters",
        "Type of ownership":  "ownership_type",
        "Industry":           "industry",
        "Sector":             "sector",
        "Revenue":            "revenue",
        "Competitors":        "competitors",
        "Easy Apply":         "easy_apply",
    })

    # ── Save ──────────────────────────────────────────────────────────────────
    out = P["processed"] / "analyst_jobs_clean.parquet"
    df.to_parquet(out, index=False)
    print(f"  Saved → {out}  ({len(df)} rows, {len(df.columns)} cols)")

    log_report({
        "source":   "analyst_jobs",
        "rows_in":  rows_in,
        "rows_out": len(df),
        "notes": (
            "Salary parsed to min/max/mid USD. "
            "Company rating stripped from name. "
            "Founded -1 → NaN. Size ordinal encoded. "
            "Rating -1 → NaN."
        ),
    }, P["report"])

    return df


if __name__ == "__main__":
    df = clean_analyst_jobs()
    print(df[["job_title", "company_name", "salary_mid",
              "company_rating", "founded_year", "size_label",
              "size_ordinal"]].head(5).to_string())
    print(f"\nShape: {df.shape}")
    print(f"Salary mid — mean: ${df['salary_mid'].mean():,.0f}")
