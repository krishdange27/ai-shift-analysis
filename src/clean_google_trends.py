# =============================================================================
# src/clean_google_trends.py
# =============================================================================
# INPUT  : data/raw/google_trends/all_keywords_combined.csv
# OUTPUT : data/processed/google_trends_clean.parquet
#
# CLEANING STEPS:
#   1. date string → datetime
#   2. All keyword columns → float (already numeric but coerce for safety)
#   3. Add pre/post ChatGPT flag (Nov 2022 cutoff)
#   4. Add year, quarter columns
#   5. Group columns into semantic buckets for easier dashboard use
#   6. NOTE on normalization: each Google Trends batch has its own 0–100 scale
#      Values are NOT comparable across keywords from different pull batches.
#      We preserve raw values and flag this in a metadata column.
# =============================================================================

from __future__ import annotations
from pathlib import Path
import pandas as pd
import sys

sys.path.insert(0, str(Path(__file__).parent))
from utils_clean import coerce_float, coerce_datetime, add_date_flags, log_report, get_paths

P = get_paths()


def clean_google_trends() -> pd.DataFrame:
    src = P["raw"] / "google_trends" / "all_keywords_combined.csv"
    print(f"Reading {src} ...")
    df = pd.read_csv(src)
    rows_in = len(df)
    print(f"  Rows in: {rows_in}")

    # ── 1. Date ───────────────────────────────────────────────────────────────
    df["date"] = coerce_datetime(df["date"])
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    # ── 2. Keyword columns → float ────────────────────────────────────────────
    keyword_cols = [c for c in df.columns if c != "date"]
    for col in keyword_cols:
        df[col] = coerce_float(df[col])

    # ── 3 & 4. Date flags ─────────────────────────────────────────────────────
    df = add_date_flags(df, "date")

    # ── 5. Semantic column groups (stored as metadata, not in df) ─────────────
    # These groups are used by the dashboard to organise dropdowns
    COLUMN_GROUPS = {
        "ai_tools":       ["ChatGPT", "Gemini", "Claude AI", "OpenAI API",
                           "LangChain", "Fine tuning LLM"],
        "ai_concepts":    ["Generative AI", "AI Assistant", "Prompt Engineering",
                           "LLM", "Machine Learning", "Deep Learning"],
        "job_roles":      ["Data Analyst jobs", "Data Scientist jobs",
                           "AI Engineer jobs", "Prompt Engineer jobs",
                           "ML Engineer jobs"],
        "traditional_tools": ["SQL tutorial", "Excel tutorial",
                              "Power BI", "Tableau", "Data Analyst"],
        "platforms":      ["Google Search", "Stack Overflow", "GitHub"],
    }

    # Save group mapping as a sidecar JSON for the dashboard
    import json
    groups_path = P["processed"] / "google_trends_column_groups.json"
    groups_path.parent.mkdir(parents=True, exist_ok=True)
    with open(groups_path, "w") as f:
        json.dump(COLUMN_GROUPS, f, indent=2)
    print(f"  Column groups saved → {groups_path}")

    # ── 6. Final column order ─────────────────────────────────────────────────
    meta_cols = ["date", "year", "quarter", "post_chatgpt", "period"]
    df = df[meta_cols + keyword_cols]

    # ── Save ──────────────────────────────────────────────────────────────────
    out = P["processed"] / "google_trends_clean.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"  Saved → {out}  ({len(df)} rows, {len(df.columns)} cols)")

    log_report({
        "source":   "google_trends",
        "rows_in":  rows_in,
        "rows_out": len(df),
        "notes":    (
            "date parsed, keyword cols coerced to float, "
            "pre/post_chatgpt flag added. "
            "WARNING: values are batch-normalised 0-100 — "
            "not comparable across keywords from different pull batches."
        ),
    }, P["report"])

    return df


if __name__ == "__main__":
    df = clean_google_trends()
    print(df.head(3).to_string())
    print(f"\nDate range: {df['date'].min()} → {df['date'].max()}")
    print(f"Post-ChatGPT rows: {df['post_chatgpt'].sum()} / {len(df)}")
