# =============================================================================
# src/clean_salary_trends.py
# =============================================================================
# INPUT  : raw/kaggle_jobs/ds_salaries_multiyear/data_science_salaries.csv
#          raw/kaggle_jobs/jobs_in_data/jobs_in_data.csv
# OUTPUT : processed/salary_trends_clean.parquet   — combined, 2020-2024
#          processed/salary_trends_yearly.parquet  — yearly aggregates per role
#
# WHAT THIS FIXES:
#   - Previously BLS salary was static 2020-2022 only
#   - These two datasets together give 15,954 rows across 2020-2024
#   - Enables salary trend analysis pre/post ChatGPT (H2, H3)
#
# CLEANING STEPS:
#   1. Combine both sources with unified schema
#   2. Map 50+ job titles → 8 standard role_category labels
#      (same labels used in linkedin_clean.parquet for consistency)
#   3. Cap salary outliers at 5th-95th percentile per role
#   4. Add post_chatgpt flag (work_year >= 2023)
#   5. Build yearly aggregate: median/mean salary per role per year
# =============================================================================

from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np
import sys

sys.path.insert(0, str(Path(__file__).parent))
from utils_clean import (coerce_float, clean_str,
                         cap_percentile, log_report, get_paths)

P = get_paths()

CHATGPT_LAUNCH_YEAR = 2023  # first full year post ChatGPT (Nov 2022)

# ── Role category mapping — same labels as linkedin_clean.parquet ─────────────
ROLE_MAP = {
    # Data Scientist
    "Data Scientist":                  "Data Scientist",
    "Applied Scientist":               "Data Scientist",
    "Research Scientist":              "Research Scientist",
    "Research Engineer":               "Research Scientist",
    "Applied Research Scientist":      "Research Scientist",

    # ML Engineer
    "Machine Learning Engineer":       "ML Engineer",
    "ML Engineer":                     "ML Engineer",
    "MLOps Engineer":                  "ML Engineer",
    "Deep Learning Engineer":          "ML Engineer",
    "NLP Engineer":                    "AI/LLM Specialist",
    "Computer Vision Engineer":        "AI/LLM Specialist",
    "AI Engineer":                     "AI Engineer",
    "AI Developer":                    "AI Engineer",
    "AI Architect":                    "AI Engineer",
    "Generative AI Engineer":          "AI/LLM Specialist",
    "LLM Engineer":                    "AI/LLM Specialist",
    "Prompt Engineer":                 "AI/LLM Specialist",

    # Data Engineer
    "Data Engineer":                   "Data Engineer",
    "Analytics Engineer":              "Data Engineer",
    "Data DevOps Engineer":            "Data Engineer",
    "ETL Developer":                   "Data Engineer",
    "Data Pipeline Engineer":          "Data Engineer",
    "DataOps Engineer":                "Data Engineer",

    # Data Analyst
    "Data Analyst":                    "Data Analyst",
    "Business Analyst":                "Data Analyst",
    "Quantitative Analyst":            "Data Analyst",
    "Financial Data Analyst":          "Data Analyst",
    "Marketing Data Analyst":          "Data Analyst",
    "Product Data Analyst":            "Data Analyst",

    # BI Analyst
    "BI Analyst":                      "BI Analyst",
    "BI Developer":                    "BI Analyst",
    "BI Data Analyst":                 "BI Analyst",
    "Business Intelligence Engineer":  "BI Analyst",
    "Power BI Developer":              "BI Analyst",

    # Data Architect
    "Data Architect":                  "Data Architect",
    "Data Modeler":                    "Data Architect",
    "Database Administrator":          "Data Architect",
    "Cloud Database Engineer":         "Data Architect",

    # Leadership
    "Data Science Manager":            "Leadership",
    "Head of Data":                    "Leadership",
    "Director of Data Science":        "Leadership",
    "Chief Data Officer":              "Leadership",
    "Data Engineering Manager":        "Leadership",
    "Head of Machine Learning":        "Leadership",
    "Machine Learning Manager":        "Leadership",
}


def map_role(title: str) -> str:
    """Map job title to standard role_category."""
    if pd.isna(title):
        return "Other"
    t = str(title).strip()
    # Exact match first
    if t in ROLE_MAP:
        return ROLE_MAP[t]
    # Fuzzy match
    tl = t.lower()
    if any(x in tl for x in ["llm", "large language", "generative ai",
                               "prompt eng", "nlp", "conversational ai"]):
        return "AI/LLM Specialist"
    if any(x in tl for x in ["machine learning", "ml eng", "mlops"]):
        return "ML Engineer"
    if "ai eng" in tl or "ai dev" in tl or "artificial intel" in tl:
        return "AI Engineer"
    if "data scien" in tl:
        return "Data Scientist"
    if "research" in tl:
        return "Research Scientist"
    if "data eng" in tl or "analytics eng" in tl:
        return "Data Engineer"
    if "data anal" in tl or "business anal" in tl:
        return "Data Analyst"
    if "architect" in tl:
        return "Data Architect"
    if any(x in tl for x in ["manager", "director", "head of", "chief", "vp "]):
        return "Leadership"
    return "Other"


# ── Load and clean DS Salaries ─────────────────────────────────────────────────

def load_ds_salaries() -> pd.DataFrame:
    path = P["raw"] / "kaggle_jobs" / "ds_salaries_multiyear" / "data_science_salaries.csv"
    df = pd.read_csv(path)
    print(f"  DS Salaries raw: {len(df):,} rows")

    df = df.rename(columns={
        "work_year":          "year",
        "job_title":          "job_title",
        "salary_in_usd":      "salary_usd",
        "experience_level":   "experience_level",
        "employment_type":    "employment_type",
        "work_models":        "work_setting",
        "company_location":   "company_location",
        "company_size":       "company_size",
    })

    # Keep relevant columns
    keep = ["year", "job_title", "salary_usd", "experience_level",
            "employment_type", "work_setting", "company_location", "company_size"]
    df = df[[c for c in keep if c in df.columns]].copy()

    df["salary_usd"] = coerce_float(df["salary_usd"])
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype(int)
    df["source"]     = "ds_salaries"

    return df


# ── Load and clean Jobs in Data ───────────────────────────────────────────────

def load_jobs_in_data() -> pd.DataFrame:
    path = P["raw"] / "kaggle_jobs" / "jobs_in_data" / "jobs_in_data.csv"
    df = pd.read_csv(path)
    print(f"  Jobs in Data raw: {len(df):,} rows")

    df = df.rename(columns={
        "work_year":          "year",
        "job_title":          "job_title",
        "salary_in_usd":      "salary_usd",
        "experience_level":   "experience_level",
        "employment_type":    "employment_type",
        "work_setting":       "work_setting",
        "company_location":   "company_location",
        "company_size":       "company_size",
    })

    keep = ["year", "job_title", "salary_usd", "experience_level",
            "employment_type", "work_setting", "company_location", "company_size"]
    df = df[[c for c in keep if c in df.columns]].copy()

    df["salary_usd"] = coerce_float(df["salary_usd"])
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype(int)
    df["source"]     = "jobs_in_data"

    return df


# ── Main clean function ───────────────────────────────────────────────────────

def clean_salary_trends():
    print("Loading salary datasets...")
    ds  = load_ds_salaries()
    jid = load_jobs_in_data()

    # Combine
    df = pd.concat([ds, jid], ignore_index=True)
    rows_in = len(df)
    print(f"\n  Combined: {rows_in:,} rows")

    # Remove duplicates (same title+year+salary across both sources)
    df = df.drop_duplicates(subset=["job_title", "year", "salary_usd"])
    print(f"  After dedup: {len(df):,} rows")

    # Map role categories
    df["role_category"] = df["job_title"].apply(map_role)

    # Cap salary outliers per role (5th–95th pct)
    print("\n  Capping salary outliers per role...")
    capped_rows = []
    for role, grp in df.groupby("role_category"):
        if len(grp) < 10:
            capped_rows.append(grp)
            continue
        lo = grp["salary_usd"].quantile(0.05)
        hi = grp["salary_usd"].quantile(0.95)
        grp = grp.copy()
        grp["salary_usd"] = grp["salary_usd"].clip(lower=lo, upper=hi)
        removed = ((grp["salary_usd"] <= 1000) | grp["salary_usd"].isna()).sum()
        print(f"    {role}: ${lo:,.0f} – ${hi:,.0f}  ({removed} removed)")
        capped_rows.append(grp)

    df = pd.concat(capped_rows, ignore_index=True)

    # Remove implausible salaries
    df = df[df["salary_usd"].between(10_000, 1_000_000)].copy()

    # Add flags
    df["post_chatgpt"] = df["year"] >= CHATGPT_LAUNCH_YEAR
    df["period"]       = df["post_chatgpt"].map(
        {True: "post_chatgpt", False: "pre_chatgpt"}
    )

    # ── Yearly aggregate per role ─────────────────────────────────────────────
    yearly = df.groupby(["year", "role_category"]).agg(
        median_salary = ("salary_usd", "median"),
        mean_salary   = ("salary_usd", "mean"),
        count         = ("salary_usd", "count"),
        p25_salary    = ("salary_usd", lambda x: x.quantile(0.25)),
        p75_salary    = ("salary_usd", lambda x: x.quantile(0.75)),
    ).reset_index()

    yearly["median_salary"] = yearly["median_salary"].round(0)
    yearly["mean_salary"]   = yearly["mean_salary"].round(0)
    yearly["post_chatgpt"]  = yearly["year"] >= CHATGPT_LAUNCH_YEAR

    # YoY salary change per role
    yearly = yearly.sort_values(["role_category", "year"])
    yearly["yoy_salary_pct"] = (
        yearly.groupby("role_category")["median_salary"]
        .pct_change() * 100
    ).round(1)

    # ── Pre/post ChatGPT summary ──────────────────────────────────────────────
    pre_post = df.groupby(["role_category", "period"]).agg(
        median_salary = ("salary_usd", "median"),
        count         = ("salary_usd", "count"),
    ).reset_index().pivot(
        index="role_category",
        columns="period",
        values=["median_salary", "count"]
    )
    pre_post.columns = ["_".join(c) for c in pre_post.columns]
    pre_post = pre_post.reset_index()
    if "median_salary_pre_chatgpt" in pre_post.columns and \
       "median_salary_post_chatgpt" in pre_post.columns:
        pre_post["salary_change_pct"] = (
            (pre_post["median_salary_post_chatgpt"] -
             pre_post["median_salary_pre_chatgpt"]) /
            pre_post["median_salary_pre_chatgpt"] * 100
        ).round(1)

    # ── Save ─────────────────────────────────────────────────────────────────
    out_main   = P["processed"] / "salary_trends_clean.parquet"
    out_yearly = P["processed"] / "salary_trends_yearly.parquet"
    out_prepost= P["processed"] / "salary_trends_prepost.parquet"

    df.to_parquet(out_main, index=False)
    yearly.to_parquet(out_yearly, index=False)
    pre_post.to_parquet(out_prepost, index=False)

    print(f"\n  ✓ salary_trends_clean.parquet    {df.shape}")
    print(f"  ✓ salary_trends_yearly.parquet   {yearly.shape}")
    print(f"  ✓ salary_trends_prepost.parquet  {pre_post.shape}")

    log_report({
        "source":   "salary_trends",
        "rows_in":  rows_in,
        "rows_out": len(df),
        "notes": (
            "Combined ds_salaries_multiyear (2020-2024) + jobs_in_data (2020-2023). "
            "Deduped on title+year+salary. Role mapped to 8 categories. "
            "Salary capped at 5th-95th pct per role. "
            "Plugs salary trend gap — replaces static BLS 2020-2022 benchmark."
        ),
    }, P["report"])

    return df, yearly, pre_post


if __name__ == "__main__":
    df, yearly, pre_post = clean_salary_trends()

    print("\n=== YEARLY MEDIAN SALARY BY ROLE ===")
    pivot = yearly.pivot(
        index="role_category", columns="year", values="median_salary"
    ).round(0)
    print(pivot.to_string())

    print("\n=== PRE vs POST ChatGPT SALARY CHANGE ===")
    cols = ["role_category", "median_salary_pre_chatgpt",
            "median_salary_post_chatgpt", "salary_change_pct"]
    cols = [c for c in cols if c in pre_post.columns]
    print(pre_post[cols].sort_values(
        "salary_change_pct", ascending=False
    ).to_string(index=False))

    print(f"\nYear distribution:")
    print(df["year"].value_counts().sort_index().to_string())

    print(f"\nRole distribution:")
    print(df["role_category"].value_counts().to_string())