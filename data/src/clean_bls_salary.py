# =============================================================================
# src/clean_bls_salary.py
# =============================================================================
# INPUT  : data/raw/bls_salary_trends_combined.csv
#          data/raw/bls_salary_yoy_summary.csv
#
# OUTPUT : data/processed/bls_salary_clean.parquet       ← cleaned trends
#          data/processed/bls_salary_summary_clean.parquet ← cleaned summary
#
# WHAT THESE FILES ARE:
#   bls_salary_trends_combined — 607 individual salary observations across
#   50 data/AI job titles, 2020–2022. One row per observation (not per person).
#
#   bls_salary_yoy_summary — aggregated mean/median/count per title per year.
#   Essentially a pre-aggregated version of the trends file.
#
# NOTE ON DATE RANGE:
#   Both files only cover 2020–2022. They are NOT joined to the master_timeline
#   as a time series. Instead they serve as a STATIC SALARY BENCHMARK TABLE
#   for role-level salary comparison in the dashboard (Analysis: salary by role).
#
# CLEANING STEPS (trends file):
#   1. Salary outlier capping — salary_usd has values from $4K to $30.4M
#      → cap at 5th–95th percentile per job title (within-title capping
#        is more accurate than global, since senior roles legitimately differ)
#   2. Map 50 job titles → ~10 standard role categories (same map as LinkedIn)
#   3. Add post_chatgpt flag (2022 is the boundary year — flag as pre)
#   4. Add salary_tier: Low / Mid / High based on within-role percentiles
#
# CLEANING STEPS (summary file):
#   1. Cap extreme mean/median salaries (global 95th pct — smaller file)
#   2. Map titles → role categories
#   3. Compute salary_growth_pct: YoY % change in median salary per title
# =============================================================================

from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np
import sys

sys.path.insert(0, str(Path(__file__).parent))
from utils_clean import (coerce_float, coerce_int, clean_str,
                         log_report, get_paths)

P = get_paths()

# ── Title → role category map ─────────────────────────────────────────────────
# Same standard roles as clean_linkedin.py for consistency across sources
TITLE_TO_ROLE = {
    # Data Scientist family
    "Data Scientist":                         "Data Scientist",
    "Lead Data Scientist":                    "Data Scientist",
    "Principal Data Scientist":               "Data Scientist",
    "Staff Data Scientist":                   "Data Scientist",
    "Applied Data Scientist":                 "Data Scientist",
    "Data Science Consultant":                "Data Scientist",
    "Data Science Manager":                   "Data Scientist",
    "Head of Data Science":                   "Data Scientist",
    "Director of Data Science":               "Data Scientist",

    # ML Engineer family
    "Machine Learning Engineer":              "ML Engineer",
    "Lead Machine Learning Engineer":         "ML Engineer",
    "Machine Learning Scientist":             "ML Engineer",
    "Applied Machine Learning Scientist":     "ML Engineer",
    "Machine Learning Developer":             "ML Engineer",
    "Machine Learning Manager":              "ML Engineer",
    "Machine Learning Infrastructure Engineer": "ML Engineer",
    "Head of Machine Learning":               "ML Engineer",

    # AI / Research family
    "AI Scientist":                           "AI Engineer",
    "Research Scientist":                     "AI Engineer",
    "NLP Engineer":                           "AI Engineer",
    "Computer Vision Engineer":               "AI Engineer",
    "Computer Vision Software Engineer":      "AI Engineer",
    "3D Computer Vision Researcher":          "AI Engineer",

    # Data Engineer family
    "Data Engineer":                          "Data Engineer",
    "Lead Data Engineer":                     "Data Engineer",
    "Principal Data Engineer":                "Data Engineer",
    "Cloud Data Engineer":                    "Data Engineer",
    "Big Data Engineer":                      "Data Engineer",
    "Data Engineering Manager":               "Data Engineer",
    "Director of Data Engineering":           "Data Engineer",
    "Data Science Engineer":                  "Data Engineer",
    "Analytics Engineer":                     "Data Engineer",
    "ETL Developer":                          "Data Engineer",

    # Data Analyst family
    "Data Analyst":                           "Data Analyst",
    "Lead Data Analyst":                      "Data Analyst",
    "Principal Data Analyst":                 "Data Analyst",
    "Product Data Analyst":                   "Data Analyst",
    "BI Data Analyst":                        "Data Analyst",
    "Business Data Analyst":                  "Data Analyst",
    "Finance Data Analyst":                   "Data Analyst",
    "Financial Data Analyst":                 "Data Analyst",
    "Marketing Data Analyst":                 "Data Analyst",
    "Data Analytics Manager":                 "Data Analyst",
    "Data Analytics Lead":                    "Data Analyst",
    "Data Analytics Engineer":                "Data Analyst",

    # Other
    "Data Architect":                         "Data Architect",
    "Big Data Architect":                     "Data Architect",
    "Data Specialist":                        "Data Analyst",
    "Head of Data":                           "Data Scientist",
}


def cap_salary_by_title(df: pd.DataFrame,
                        col: str = "salary_usd",
                        lower: float = 0.05,
                        upper: float = 0.95) -> pd.DataFrame:
    """
    Cap salary within each job title at given percentiles.
    Within-title capping is fairer than global — a $500K senior DS salary
    is not an outlier globally but a $30M entry is.
    """
    df = df.copy()
    def _cap(grp):
        lo = grp[col].quantile(lower)
        hi = grp[col].quantile(upper)
        grp[col] = grp[col].clip(lower=lo, upper=hi)
        return grp
    return df.groupby("job_title", group_keys=False).apply(_cap)


def add_salary_tier(df: pd.DataFrame,
                    col: str = "salary_usd") -> pd.DataFrame:
    """
    Add salary_tier (Low / Mid / High) based on within-role-category
    33rd and 67th percentiles.
    """
    df = df.copy()
    def _tier(grp):
        p33 = grp[col].quantile(0.33)
        p67 = grp[col].quantile(0.67)
        grp["salary_tier"] = pd.cut(
            grp[col],
            bins=[-np.inf, p33, p67, np.inf],
            labels=["Low", "Mid", "High"]
        )
        return grp
    return df.groupby("role_category", group_keys=False).apply(_tier)


# ─────────────────────────────────────────────────────────────────────────────
# CLEAN TRENDS FILE
# ─────────────────────────────────────────────────────────────────────────────

def clean_bls_trends() -> pd.DataFrame:
    src = P["raw"] / "bls" / "bls_salary_trends_combined.csv"
    print(f"Reading {src} ...")
    df = pd.read_csv(src)
    rows_in = len(df)
    print(f"  Rows in: {rows_in}")
    print(f"  Salary range before cap: "
          f"${df['salary_usd'].min():,.0f} – ${df['salary_usd'].max():,.0f}")

    # ── 1. Basic coercions ────────────────────────────────────────────────────
    df["year"]       = coerce_int(df["year"])
    df["salary_usd"] = coerce_float(df["salary_usd"])
    df["job_title"]  = clean_str(df["job_title"])
    df = df.dropna(subset=["salary_usd", "job_title", "year"])

    # ── 2. Within-title outlier capping ───────────────────────────────────────
    df = cap_salary_by_title(df, col="salary_usd", lower=0.05, upper=0.95)
    print(f"  Salary range after cap:  "
          f"${df['salary_usd'].min():,.0f} – ${df['salary_usd'].max():,.0f}")

    # ── 3. Map titles → role categories ──────────────────────────────────────
    df["role_category"] = df["job_title"].map(TITLE_TO_ROLE).fillna("Other")
    unmapped = df[df["role_category"] == "Other"]["job_title"].unique()
    if len(unmapped):
        print(f"  Unmapped titles ({len(unmapped)}): {list(unmapped)}")

    # ── 4. Salary tier within role ────────────────────────────────────────────
    df = add_salary_tier(df, col="salary_usd")

    # ── 5. pre/post ChatGPT flag ──────────────────────────────────────────────
    # All data is 2020–2022 — all pre ChatGPT (Nov 2022)
    # Flag 2022 separately as "transition year"
    df["post_chatgpt"]    = False
    df["period"]          = "pre_chatgpt"
    df["transition_year"] = df["year"] == 2022

    # ── 6. Drop source col (only one source anyway) ───────────────────────────
    df = df.drop(columns=["source"], errors="ignore")

    # ── Final column order ────────────────────────────────────────────────────
    df = df[["year", "job_title", "role_category", "salary_usd",
             "salary_tier", "post_chatgpt", "period", "transition_year"]]

    rows_out = len(df)
    print(f"  Rows out: {rows_out}")

    out = P["processed"] / "bls_salary_clean.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"  Saved → {out}")

    log_report({
        "source":   "bls_salary_trends",
        "rows_in":  rows_in,
        "rows_out": rows_out,
        "notes": (
            "Within-title salary capping at 5th–95th pct. "
            "50 titles mapped to ~8 role categories. "
            "salary_tier (Low/Mid/High) added within each role_category. "
            "All rows are pre-ChatGPT (2020–2022). "
            "Used as static salary benchmark — not joined to master_timeline."
        ),
    }, P["report"])

    return df


# ─────────────────────────────────────────────────────────────────────────────
# CLEAN SUMMARY FILE
# ─────────────────────────────────────────────────────────────────────────────

def clean_bls_summary() -> pd.DataFrame:
    src = P["raw"] / "bls" / "bls_salary_yoy_summary.csv"
    print(f"\nReading {src} ...")
    df = pd.read_csv(src)
    rows_in = len(df)
    print(f"  Rows in: {rows_in}")

    # ── 1. Coerce ─────────────────────────────────────────────────────────────
    df["year"]          = coerce_int(df["year"])
    df["mean_salary"]   = coerce_float(df["mean_salary"])
    df["median_salary"] = coerce_float(df["median_salary"])
    df["count"]         = coerce_int(df["count"])
    df["job_title"]     = clean_str(df["job_title"])
    df = df.dropna(subset=["median_salary", "job_title", "year"])

    # ── 2. Global cap at 95th pct (smaller file, global is fine here) ─────────
    cap_95 = df["median_salary"].quantile(0.95)
    cap_95_mean = df["mean_salary"].quantile(0.95)
    before_outliers = (df["median_salary"] > cap_95).sum()
    df["median_salary"] = df["median_salary"].clip(upper=cap_95)
    df["mean_salary"]   = df["mean_salary"].clip(upper=cap_95_mean)
    print(f"  Capped {before_outliers} rows above ${cap_95:,.0f} median")

    # ── 3. Map titles → role categories ──────────────────────────────────────
    df["role_category"] = df["job_title"].map(TITLE_TO_ROLE).fillna("Other")

    # ── 4. YoY % change in median salary per job title ───────────────────────
    df = df.sort_values(["job_title", "year"]).reset_index(drop=True)
    df["salary_yoy_pct"] = (
        df.groupby("job_title")["median_salary"]
          .pct_change() * 100
    ).round(2)

    # ── 5. Role-level aggregates (collapses 50 titles → 8 roles) ─────────────
    role_summary = (
        df.groupby(["role_category", "year"])
          .agg(
              role_median_salary = ("median_salary", "median"),
              role_mean_salary   = ("mean_salary",   "mean"),
              role_sample_count  = ("count",         "sum"),
              role_title_count   = ("job_title",     "nunique"),
          )
          .reset_index()
    )
    # YoY for role-level too
    role_summary = role_summary.sort_values(["role_category", "year"])
    role_summary["role_salary_yoy_pct"] = (
        role_summary.groupby("role_category")["role_median_salary"]
                    .pct_change() * 100
    ).round(2)

    print(f"\n  Role-level summary ({len(role_summary)} rows):")
    print(role_summary.to_string(index=False))

    # ── Save both ─────────────────────────────────────────────────────────────
    out_title = P["processed"] / "bls_salary_summary_clean.parquet"
    out_role  = P["processed"] / "bls_salary_role_summary.parquet"

    df.to_parquet(out_title, index=False)
    role_summary.to_parquet(out_role, index=False)

    print(f"\n  Saved title-level → {out_title}  ({len(df)} rows)")
    print(f"  Saved role-level  → {out_role}   ({len(role_summary)} rows)")

    log_report({
        "source":   "bls_salary_summary",
        "rows_in":  rows_in,
        "rows_out": len(df),
        "notes": (
            "Global 95th pct cap on median/mean salary. "
            "50 titles mapped to ~8 role categories. "
            "YoY % salary change added per title and per role. "
            "Role-level summary saved separately as bls_salary_role_summary.parquet."
        ),
    }, P["report"])

    return df, role_summary


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("CLEANING BLS SALARY DATA")
    print("=" * 60)

    trends = clean_bls_trends()

    print("\n--- Trends sample ---")
    print(trends.head(5).to_string())
    print(f"\nRole category distribution:")
    print(trends["role_category"].value_counts())
    print(f"\nMedian salary by role + year:")
    print(
        trends.groupby(["role_category", "year"])["salary_usd"]
              .median()
              .unstack()
              .round(0)
              .to_string()
    )

    print("\n" + "=" * 60)

    summary, role_summary = clean_bls_summary()

    print("\n--- Summary sample ---")
    print(summary[["job_title", "year", "median_salary",
                   "salary_yoy_pct", "role_category"]].head(8).to_string())
