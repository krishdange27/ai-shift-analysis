# =============================================================================
# src/clean_stackoverflow.py
# =============================================================================
# INPUT  : data/raw/stackoverflow/survey_all_years_combined.csv
# OUTPUT : data/processed/stackoverflow_clean.parquet
#          data/processed/stackoverflow_skills_long.parquet
#
# CLEANING STEPS:
#   1. YearsCode strings → numeric (Less than 1 year → 0.5, More than 50 → 50)
#   2. ConvertedCompYearly → float, cap at 99th percentile (extreme outliers)
#   3. AISelect: only exists from 2023 → handled year-aware (NaN for prior years)
#   4. Employment, EdLevel, MainBranch, DevType → clean strings
#   5. Explode LanguageHaveWorkedWith (semicolon) → long table
#   6. Explode DevType (semicolon) → long table
#   7. Add pre/post ChatGPT flag via survey_year
#   8. Align / drop columns not consistent across years
# =============================================================================

from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np
import sys

sys.path.insert(0, str(Path(__file__).parent))
from utils_clean import (coerce_float, coerce_int, clean_str,
                         parse_years_code, cap_percentile,
                         explode_semicolon, add_date_flags,
                         log_report, get_paths, CHATGPT_LAUNCH)

P = get_paths()


def clean_stackoverflow() -> tuple[pd.DataFrame, pd.DataFrame]:
    src = P["raw"] / "stackoverflow" / "survey_all_years_combined.csv"
    print(f"Reading {src} ...")
    df = pd.read_csv(src, low_memory=False)
    rows_in = len(df)
    print(f"  Rows in: {rows_in}")

    # ── 1. YearsCode → numeric ────────────────────────────────────────────────
    df["years_code"] = parse_years_code(df["YearsCode"])
    df = df.drop(columns=["YearsCode"])
    print(f"  years_code parsed — NaN rate: "
          f"{df['years_code'].isna().mean():.1%}")

    # ── 2. Compensation → float, cap outliers ─────────────────────────────────
    df["comp_yearly"] = coerce_float(df["ConvertedCompYearly"])
    # Only cap non-null values
    valid_mask = df["comp_yearly"].notna()
    df.loc[valid_mask, "comp_yearly"] = cap_percentile(
        df.loc[valid_mask, "comp_yearly"], lower=0.01, upper=0.99
    )
    df = df.drop(columns=["ConvertedCompYearly", "CompTotal"], errors="ignore")
    print(f"  comp_yearly capped at 99th pct: "
          f"${df['comp_yearly'].max():,.0f}")

    # ── 3. AISelect — year-aware handling ─────────────────────────────────────
    # Column only exists from survey_year 2023+
    # For earlier years it will be NaN already; just clean and flag
    if "AISelect" in df.columns:
        df["ai_select"] = clean_str(df["AISelect"])
        # Confirm: years before 2023 should be NaN
        early_filled = (
            df[df["survey_year"] < 2023]["ai_select"].notna().sum()
        )
        if early_filled > 0:
            print(f"  WARNING: AISelect has {early_filled} non-null rows "
                  f"in pre-2023 data — setting to NaN")
            df.loc[df["survey_year"] < 2023, "ai_select"] = np.nan
        df = df.drop(columns=["AISelect"])
    else:
        df["ai_select"] = np.nan

    if "AIAcc" in df.columns:
        df["ai_acc"] = clean_str(df["AIAcc"])
        df = df.drop(columns=["AIAcc"])
    else:
        df["ai_acc"] = np.nan

    # ── 4. Clean string columns ───────────────────────────────────────────────
    str_cols = {
        "Country":    "country",
        "EdLevel":    "ed_level",
        "Employment": "employment",
        "MainBranch": "main_branch",
        "Currency":   "currency",
    }
    for old, new in str_cols.items():
        if old in df.columns:
            df[new] = clean_str(df[old])
            df = df.drop(columns=[old])

    # ── 5. Pre/post ChatGPT via survey_year ───────────────────────────────────
    df["survey_year"] = coerce_int(df["survey_year"])
    # survey_year 2023+ = post ChatGPT (launched Nov 2022, first full year 2023)
    df["post_chatgpt"] = df["survey_year"] >= 2023
    df["period"] = np.where(df["post_chatgpt"], "post_chatgpt", "pre_chatgpt")

    # ── 6. Keep only useful columns ───────────────────────────────────────────
    keep_cols = [
        "ResponseId", "survey_year", "country", "ed_level", "employment",
        "main_branch", "years_code", "comp_yearly", "currency",
        "ai_select", "ai_acc", "post_chatgpt", "period",
        "LanguageHaveWorkedWith", "LanguageWantToWorkWith",
        "DatabaseHaveWorkedWith", "DevType",
    ]
    keep_cols = [c for c in keep_cols if c in df.columns]
    df = df[keep_cols]

    # ── 7. Explode skills → long table ────────────────────────────────────────
    skills_frames = []

    for col, skill_type in [
        ("LanguageHaveWorkedWith", "language_used"),
        ("LanguageWantToWorkWith", "language_want"),
        ("DatabaseHaveWorkedWith", "database_used"),
        ("DevType",                "dev_type"),
    ]:
        if col not in df.columns:
            continue
        long = explode_semicolon(
            df, id_col=["ResponseId", "survey_year", "post_chatgpt", "period"],
            value_col=col, new_col="value"
        )
        long["skill_type"] = skill_type
        skills_frames.append(long)
        print(f"  Exploded {col}: {len(long)} rows")

    skills_long = pd.concat(skills_frames, ignore_index=True) if skills_frames else pd.DataFrame()

    # Drop raw semicolon columns from main df
    df = df.drop(columns=[
        "LanguageHaveWorkedWith", "LanguageWantToWorkWith",
        "DatabaseHaveWorkedWith", "DevType"
    ], errors="ignore")

    # ── Save ──────────────────────────────────────────────────────────────────
    out_main  = P["processed"] / "stackoverflow_clean.parquet"
    out_long  = P["processed"] / "stackoverflow_skills_long.parquet"

    df.to_parquet(out_main, index=False)
    print(f"  Saved main → {out_main}  ({len(df)} rows, {len(df.columns)} cols)")

    if not skills_long.empty:
        skills_long.to_parquet(out_long, index=False)
        print(f"  Saved long → {out_long}  ({len(skills_long)} rows)")

    log_report({
        "source":   "stackoverflow",
        "rows_in":  rows_in,
        "rows_out": len(df),
        "notes": (
            "YearsCode str→numeric. CompYearly capped at 99th pct. "
            "AISelect NaN enforced for pre-2023 rows. "
            "Skills exploded to stackoverflow_skills_long.parquet. "
            "post_chatgpt flag based on survey_year >= 2023."
        ),
    }, P["report"])

    return df, skills_long


if __name__ == "__main__":
    df, skills = clean_stackoverflow()
    print(df.head(3).to_string())
    print(f"\nMain shape: {df.shape}")
    print(f"Skills long shape: {skills.shape}")
    print(f"\nPost-ChatGPT rows: {df['post_chatgpt'].sum():,} / {len(df):,}")
    print(f"\nAI Select distribution (2023+):")
    print(df[df["post_chatgpt"]]["ai_select"].value_counts().head(10))
    print(f"\nTop languages (used):")
    print(skills[skills["skill_type"] == "language_used"]["value"].value_counts().head(10))
