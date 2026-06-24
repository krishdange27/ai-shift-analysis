# =============================================================================
# src/build_master_timeline.py  (FIXED)
# =============================================================================
# FIXES vs original:
#   - agg_stackoverflow: so_pct_ai_users uses startswith("yes") to handle
#     both 2023 ("Yes") and 2025 ("Yes, I use AI tools daily/weekly/monthly")
#   - agg_linkedin: reads linkedin_tech_only.parquet instead of full dataset
#     so li_* columns reflect tech jobs only, not nurses/sales managers
# All other logic identical to original.
# =============================================================================

from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np
import sys

sys.path.insert(0, str(Path(__file__).parent))
from utils_clean import (add_date_flags, add_covid_flag,
                         log_report, get_paths, CHATGPT_LAUNCH)

P = get_paths()


def make_backbone() -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", "2026-06-01", freq="MS")
    df = pd.DataFrame({"date": dates})
    df = add_date_flags(df, "date")
    df = add_covid_flag(df, "date")
    return df


def agg_google_trends() -> pd.DataFrame:
    path = P["processed"] / "google_trends_clean.parquet"
    if not path.exists():
        print("  SKIP google_trends (not found)")
        return pd.DataFrame()
    df = pd.read_parquet(path)
    meta = ["date", "year", "quarter", "post_chatgpt", "period",
            "covid_period"]
    kw_cols = [c for c in df.columns if c not in meta]
    return df[["date"] + kw_cols].copy()


def agg_fred() -> pd.DataFrame:
    path = P["processed"] / "fred_clean.parquet"
    if not path.exists():
        print("  SKIP fred (not found)")
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df = df[df["date"] >= "2020-01-01"]
    drop_meta = ["year", "quarter", "post_chatgpt", "period", "covid_period"]
    df = df.drop(columns=[c for c in drop_meta if c in df.columns])
    return df.copy()


def agg_stackoverflow() -> pd.DataFrame:
    """
    FIX: so_pct_ai_users uses startswith('yes') instead of exact match.
    Handles both:
      2023: "Yes"
      2025: "Yes, I use AI tools daily" / "Yes, I use AI tools weekly" / etc.
    """
    path       = P["processed"] / "stackoverflow_clean.parquet"
    skills_path = P["processed"] / "stackoverflow_skills_long.parquet"
    if not path.exists():
        print("  SKIP stackoverflow (not found)")
        return pd.DataFrame()

    df = pd.read_parquet(path)
    df = df[df["survey_year"].notna()]
    df["survey_year"] = df["survey_year"].astype(int)

    # FIX: startswith("yes") catches all variants across years
    def uses_ai(val) -> bool:
        if pd.isna(val):
            return False
        return str(val).strip().lower().startswith("yes")

    df["_uses_ai"] = df["ai_select"].apply(uses_ai)

    yearly = df.groupby("survey_year").agg(
        so_respondents        = ("ResponseId",   "count"),
        so_median_comp        = ("comp_yearly",  "median"),
        so_mean_comp          = ("comp_yearly",  "mean"),
        so_pct_ai_users       = ("_uses_ai",     lambda x: x.mean() * 100),
        so_median_years_code  = ("years_code",   "median"),
    ).reset_index()

    # Round for cleanliness
    yearly["so_pct_ai_users"] = yearly["so_pct_ai_users"].round(1)
    yearly["so_median_comp"]  = yearly["so_median_comp"].round(0)
    yearly["so_mean_comp"]    = yearly["so_mean_comp"].round(0)

    if skills_path.exists():
        sk = pd.read_parquet(skills_path)
        sk = sk[sk["skill_type"] == "language_used"]
        top_lang = (
            sk.groupby(["survey_year", "value"])
              .size()
              .reset_index(name="n")
              .sort_values(["survey_year", "n"], ascending=[True, False])
              .groupby("survey_year").first()
              .reset_index()
              .rename(columns={"value": "so_top_language"})
            [["survey_year", "so_top_language"]]
        )
        yearly = yearly.merge(top_lang, on="survey_year", how="left")

    print(f"  SO ai adoption by year:")
    print(yearly[["survey_year", "so_respondents",
                  "so_pct_ai_users"]].to_string(index=False))

    # Spread yearly values across months
    months = pd.date_range("2020-01-01", "2026-06-01", freq="MS")
    rows = []
    for month in months:
        yr = month.year
        row_data = yearly[yearly["survey_year"] == yr]
        if row_data.empty:
            rows.append({"date": month})
        else:
            r = row_data.iloc[0].to_dict()
            r["date"] = month
            rows.append(r)

    out = pd.DataFrame(rows)
    out = out.drop(columns=["survey_year"], errors="ignore")
    return out


def agg_linkedin() -> pd.DataFrame:
    """
    FIX: reads linkedin_tech_only.parquet instead of linkedin_clean.parquet
    so monthly aggregates reflect tech/data jobs only.
    Falls back to linkedin_clean.parquet if tech_only doesn't exist yet.
    """
    tech_path = P["processed"] / "linkedin_tech_only.parquet"
    full_path  = P["processed"] / "linkedin_clean.parquet"

    if tech_path.exists():
        df = pd.read_parquet(tech_path)
        print(f"  LinkedIn: using tech_only ({len(df):,} rows)")
    elif full_path.exists():
        df = pd.read_parquet(full_path)
        print(f"  LinkedIn: using full dataset ({len(df):,} rows) — run fixed clean_linkedin.py for better results")
    else:
        print("  SKIP linkedin (not found)")
        return pd.DataFrame()

    df["listed_date"] = pd.to_datetime(df["listed_date"])
    df["month"] = df["listed_date"].dt.to_period("M").dt.to_timestamp()

    monthly = df.groupby("month").agg(
        li_job_postings  = ("job_id",         "count"),
        li_median_salary = ("mid_salary",      "median"),
        li_mean_ai_score = ("ai_skill_score",  "mean"),
        li_pct_ai_jobs   = ("ai_skill_score",
                             lambda x: (x > 0).mean() * 100),
        li_pct_remote    = ("remote_allowed",
                             lambda x: pd.to_numeric(
                                 x, errors="coerce").mean() * 100),
    ).reset_index().rename(columns={"month": "date"})

    # Round
    monthly["li_mean_ai_score"] = monthly["li_mean_ai_score"].round(2)
    monthly["li_pct_ai_jobs"]   = monthly["li_pct_ai_jobs"].round(1)
    monthly["li_pct_remote"]    = monthly["li_pct_remote"].round(1)

    # Top role per month (exclude Other)
    top_role = (
        df[df["role_category"] != "Other"]
        .groupby(["month", "role_category"])
        .size()
        .reset_index(name="n")
        .sort_values(["month", "n"], ascending=[True, False])
        .groupby("month").first()
        .reset_index()
        .rename(columns={"month": "date", "role_category": "li_top_role"})
        [["date", "li_top_role"]]
    )
    monthly = monthly.merge(top_role, on="date", how="left")

    print(f"  LinkedIn monthly rows: {len(monthly)}")
    print(f"  Date range: {monthly['date'].min().date()} "
          f"→ {monthly['date'].max().date()}")

    return monthly


def load_bls_reference() -> dict[str, pd.DataFrame]:
    """Load BLS salary reference tables for dashboard use (not joined to timeline)."""
    out = {}
    paths = {
        "trends":        P["processed"] / "bls_salary_clean.parquet",
        "title_summary": P["processed"] / "bls_salary_summary_clean.parquet",
        "role_summary":  P["processed"] / "bls_salary_role_summary.parquet",
    }
    for key, path in paths.items():
        if path.exists():
            out[key] = pd.read_parquet(path)
            print(f"  BLS {key}: {len(out[key])} rows")
        else:
            print(f"  BLS {key}: NOT FOUND")
            out[key] = pd.DataFrame()
    return out


def build_master_timeline() -> pd.DataFrame:
    print("Building master timeline ...")
    backbone = make_backbone()
    print(f"  Backbone: {len(backbone)} months")

    sources = {
        "google_trends": agg_google_trends,
        "fred":          agg_fred,
        "stackoverflow": agg_stackoverflow,
        "linkedin":      agg_linkedin,
    }

    master = backbone.copy()
    for name, fn in sources.items():
        print(f"\n  Aggregating {name} ...")
        agg = fn()
        if agg.empty:
            continue
        master = master.merge(agg, on="date", how="left")
        print(f"    Shape now: {master.shape}")

    # Clean up duplicate meta columns from merges
    dup = ["year_y","quarter_y","post_chatgpt_y","period_y","covid_period_y"]
    master = master.drop(columns=[c for c in dup if c in master.columns])
    master = master.rename(columns={
        c: c.replace("_x", "") for c in master.columns if c.endswith("_x")
    })
    master = master.sort_values("date").reset_index(drop=True)

    out = P["processed"] / "master_timeline.parquet"
    master.to_parquet(out, index=False)

    print(f"\n  Saved → {out}")
    print(f"  Shape: {master.shape}")

    log_report({
        "source":   "master_timeline",
        "rows_in":  len(backbone),
        "rows_out": len(master),
        "notes": (
            "FIXED: SO ai adoption uses startswith('yes'). "
            "LinkedIn uses tech_only subset."
        ),
    }, P["report"])

    return master


if __name__ == "__main__":
    master = build_master_timeline()

    print("\n--- SO ai adoption check ---")
    so_check = master.groupby("year")["so_pct_ai_users"].first().dropna()
    print(so_check.to_string())

    print("\n--- LinkedIn monthly check ---")
    li_check = master[master["li_job_postings"].notna()][
        ["date","li_job_postings","li_mean_ai_score",
         "li_pct_ai_jobs","li_top_role"]
    ]
    print(li_check.to_string(index=False))

    print("\n--- BLS reference ---")
    bls = load_bls_reference()
    for k, v in bls.items():
        print(f"  {k}: {v.shape}")
