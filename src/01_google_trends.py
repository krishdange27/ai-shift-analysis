"""
Script 1: Google Trends Data Collector
=======================================
Pulls search interest over time for all AI and baseline keywords.
Uses pytrends (unofficial Google Trends API wrapper).

Install: pip install pytrends pandas
Run:     python src/01_google_trends.py
Output:  data/raw/google_trends/
"""

import time
import pandas as pd
from pytrends.request import TrendReq
from pytrends.exceptions import ResponseError
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

OUTPUT_DIR = Path("data/raw/google_trends")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# pytrends only allows 5 keywords per request — we batch them
KEYWORD_BATCHES = {
    "ai_tools": ["ChatGPT", "Gemini", "Claude AI", "Generative AI", "AI Assistant"],
    "ai_skills": ["Prompt Engineering", "LangChain", "LLM", "OpenAI API", "Fine tuning LLM"],
    "traditional_skills": ["SQL tutorial", "Excel tutorial", "Power BI", "Tableau", "Data Analyst"],
    "job_search": ["Data Scientist jobs", "AI Engineer jobs", "Prompt Engineer jobs", "ML Engineer jobs", "Data Analyst jobs"],
    "baselines": ["Google Search", "Stack Overflow", "GitHub", "Machine Learning", "Deep Learning"],
}

# Timeframe: Jan 2020 to present — captures pre/post ChatGPT (Nov 2022)
TIMEFRAME = "2020-01-01 2026-06-01"
GEO = ""  # worldwide; change to "US" for US-only

# ── Helper ────────────────────────────────────────────────────────────────────

def fetch_with_retry(pytrends, keywords, timeframe, geo, retries=3, wait=60):
    """Fetch interest_over_time with retry logic for rate limits (429 errors)."""
    for attempt in range(1, retries + 1):
        try:
            pytrends.build_payload(keywords, timeframe=timeframe, geo=geo)
            df = pytrends.interest_over_time()
            if df.empty:
                print(f"  [WARN] Empty response for {keywords}")
                return None
            return df
        except ResponseError as e:
            if "429" in str(e) and attempt < retries:
                print(f"  [RATE LIMIT] Waiting {wait}s before retry {attempt}/{retries}...")
                time.sleep(wait)
                wait *= 2  # exponential backoff
            else:
                print(f"  [ERROR] Failed after {retries} attempts: {e}")
                return None
        except Exception as e:
            print(f"  [ERROR] Unexpected error: {e}")
            return None

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  Google Trends Collector — AI Shift Project")
    print("=" * 55)

    # hl=en-US: response language | tz=0: UTC timezone
    pytrends = TrendReq(hl="en-US", tz=0, timeout=(10, 25), retries=2, backoff_factor=0.5)

    all_frames = []

    for batch_name, keywords in KEYWORD_BATCHES.items():
        print(f"\n[{batch_name}] Fetching: {keywords}")

        df = fetch_with_retry(pytrends, keywords, TIMEFRAME, GEO)

        if df is not None:
            # Drop the 'isPartial' column Google adds for the current incomplete week
            if "isPartial" in df.columns:
                df = df.drop(columns=["isPartial"])

            df.index.name = "date"
            df.reset_index(inplace=True)

            out_path = OUTPUT_DIR / f"{batch_name}.csv"
            df.to_csv(out_path, index=False)
            print(f"  ✓ Saved {len(df)} rows → {out_path}")

            all_frames.append(df.set_index("date"))

        # Google Trends rate limits aggressively — always pause between batches
        print("  Sleeping 8s to respect rate limits...")
        time.sleep(8)

    # Merge all batches on date index into one wide CSV
    if all_frames:
        combined = pd.concat(all_frames, axis=1)
        combined.reset_index(inplace=True)
        combined_path = OUTPUT_DIR / "all_keywords_combined.csv"
        combined.to_csv(combined_path, index=False)
        print(f"\n✓ Combined file saved → {combined_path}")
        print(f"  Shape: {combined.shape[0]} weeks × {combined.shape[1]} columns")

    print("\nDone. Check data/raw/google_trends/")


if __name__ == "__main__":
    main()
