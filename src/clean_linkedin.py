# =============================================================================
# src/clean_linkedin.py  (FIXED)
# =============================================================================
# INPUT  : data/raw/kaggle_jobs/linkedin_job_postings/postings.csv
# OUTPUT : data/processed/linkedin_clean.parquet
#          data/processed/linkedin_tech_only.parquet   ← NEW
#          data/processed/linkedin_skills_long.parquet
#
# FIXES vs original:
#   - TITLE_MAP expanded with broader patterns + ordered correctly
#   - is_tech_job flag added (title OR description has tech signals)
#   - ai_skill_score uses unique keyword set match (not findall)
#   - linkedin_tech_only.parquet saved separately for dashboard use
# =============================================================================

from __future__ import annotations
from pathlib import Path
import re
import pandas as pd
import numpy as np
import sys

sys.path.insert(0, str(Path(__file__).parent))
from utils_clean import (coerce_float, clean_str, coerce_unix_ms,
                         add_date_flags, explode_semicolon,
                         log_report, get_paths)

P = get_paths()

KEEP_COLS = [
    "job_id", "company_name", "title", "description",
    "min_salary", "max_salary", "med_salary", "normalized_salary",
    "pay_period", "location", "formatted_work_type",
    "formatted_experience_level", "remote_allowed",
    "listed_time", "skills_desc",
]

# ── FIXED: Title map — ordered broad→specific, covers more variants ────────────
# First match wins — more specific patterns must come before broader ones
TITLE_MAP = [
    # AI/LLM specialist — before "engineer" patterns to avoid misclassification
    (r"llm|large\s+language|generative\s+ai|gen\s*ai|genai"
     r"|prompt\s+eng|nlp\s+eng|conversational\s+ai",    "AI/LLM Specialist"),

    # AI Engineer — before generic "engineer"
    (r"ai\s+eng|a\.i\.\s+eng|artificial\s+intel.*eng"
     r"|applied\s+(ai|scientist)|ml\s+ops|mlops",        "AI Engineer"),

    # Research Scientist — before data scientist
    (r"research\s+sci|research\s+eng|ai\s+research"
     r"|applied\s+research",                              "Research Scientist"),

    # Data Scientist
    (r"data\s+scien",                                     "Data Scientist"),

    # ML Engineer
    (r"machine\s+learn.*eng|ml\s+eng|deep\s+learn.*eng", "ML Engineer"),

    # Data Engineer
    (r"data\s+eng|analytics\s+eng|etl\s+dev|data\s+platform"
     r"|data\s+pipeline|dbt\s+eng",                      "Data Engineer"),

    # BI Analyst — before data analyst (more specific)
    (r"bi\s+anal|business\s+intel.*anal|power\s+bi\s+dev"
     r"|tableau\s+dev|looker\s+dev|reporting\s+anal",    "BI Analyst"),

    # Data Analyst — broad
    (r"data\s+anal|analytics\s+anal|business\s+anal"
     r"|quantitative\s+anal",                            "Data Analyst"),

    # Software Engineer — broad
    (r"software\s+eng|software\s+dev|swe\b|back.?end\s+eng"
     r"|front.?end\s+eng|full.?stack|web\s+dev"
     r"|platform\s+eng|site\s+reliab",                  "Software Engineer"),

    # DevOps/Cloud
    (r"devops|cloud\s+eng|infrastructure\s+eng"
     r"|solutions?\s+arch|cloud\s+arch|sre\b",          "DevOps/Cloud Engineer"),

    # Product Manager
    (r"product\s+manag|product\s+owner|\bpm\b(?!.*project)",  "Product Manager"),
]

# Tech signals for is_tech_job flag (title OR description)
TECH_SIGNALS = re.compile(
    r"python|sql|machine\s+learn|data\s+sci|data\s+eng|software\s+eng"
    r"|tensorflow|pytorch|spark|hadoop|kubernetes|docker|aws|azure|gcp"
    r"|scikit|pandas|numpy|jupyter|databricks|airflow|kafka|dbt"
    r"|deep\s+learn|neural\s+net|llm|nlp|data\s+anal|bi\s+anal"
    r"|analytics|tableau|power\s+bi|looker|scikit.learn",
    re.IGNORECASE
)

# AI keywords — use set of compiled patterns, score = # unique matches
AI_KEYWORDS = [
    r"machine\s+learn", r"deep\s+learn", r"artificial\s+intel",
    r"neural\s+net", r"\bllm\b", r"large\s+language\s+model",
    r"generative\s+ai", r"chatgpt", r"openai", r"langchain",
    r"prompt\s+eng", r"\bnlp\b", r"natural\s+language",
    r"computer\s+vision", r"tensorflow", r"pytorch", r"scikit",
    r"hugging\s+face", r"fine.tun", r"rag\b",
    r"retrieval.augmented", r"vector\s+database", r"embedding",
    r"\bcopilot\b", r"stable\s+diffusion", r"foundation\s+model",
]
AI_PATTERNS = [re.compile(kw, re.IGNORECASE) for kw in AI_KEYWORDS]


def normalise_title(title: str) -> str:
    if pd.isna(title):
        return "Other"
    t = str(title).lower().strip()
    for pattern, label in TITLE_MAP:
        if re.search(pattern, t, re.IGNORECASE):
            return label
    return "Other"


def is_tech_job(title: str, description: str) -> bool:
    """True if title OR description contains tech signals."""
    text = f"{title} {description}" if not pd.isna(description) else str(title)
    return bool(TECH_SIGNALS.search(text))


def ai_skill_score(text: str) -> int:
    """Count distinct AI keyword pattern matches in description."""
    if pd.isna(text):
        return 0
    t = str(text)
    return sum(1 for pat in AI_PATTERNS if pat.search(t))


def process_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    chunk = chunk[[c for c in KEEP_COLS if c in chunk.columns]].copy()

    # listed_time: Unix ms → datetime
    chunk["listed_date"] = coerce_unix_ms(chunk["listed_time"])
    chunk = chunk.drop(columns=["listed_time"])

    # Filter to 2020–2024
    chunk = chunk[chunk["listed_date"].dt.year.between(2020, 2024)]
    if chunk.empty:
        return chunk

    # Salary → float
    for col in ["min_salary", "max_salary", "med_salary", "normalized_salary"]:
        if col in chunk.columns:
            chunk[col] = coerce_float(chunk[col])

    # Derive mid_salary
    chunk["mid_salary"] = np.where(
        chunk["med_salary"].notna(),
        chunk["med_salary"],
        np.where(
            chunk["min_salary"].notna() & chunk["max_salary"].notna(),
            (chunk["min_salary"] + chunk["max_salary"]) / 2,
            chunk["normalized_salary"],
        )
    )

    # FIX: expanded title normalisation
    chunk["role_category"] = chunk["title"].apply(normalise_title)

    # FIX: is_tech_job uses title + description
    chunk["is_tech_job"] = chunk.apply(
        lambda r: is_tech_job(r["title"], r.get("description", "")), axis=1
    )
    # Any non-Other role is definitely a tech job
    chunk.loc[chunk["role_category"] != "Other", "is_tech_job"] = True

    # FIX: ai_skill_score uses unique pattern matching
    chunk["ai_skill_score"] = chunk["description"].apply(ai_skill_score)

    # Clean strings
    for col in ["company_name", "location", "formatted_work_type",
                "formatted_experience_level"]:
        if col in chunk.columns:
            chunk[col] = clean_str(chunk[col])

    # Drop description + raw salary cols
    chunk = chunk.drop(
        columns=["description", "med_salary", "normalized_salary"],
        errors="ignore"
    )
    return chunk


def clean_linkedin() -> tuple[pd.DataFrame, pd.DataFrame]:
    src = P["raw"] / "kaggle_jobs" / "linkedin_job_postings" / "postings.csv"
    print(f"Streaming {src} in 100k-row chunks ...")

    chunks = []
    rows_in = 0
    chunk_num = 0

    for chunk in pd.read_csv(src, chunksize=100_000, low_memory=False):
        rows_in += len(chunk)
        chunk_num += 1
        processed = process_chunk(chunk)
        if not processed.empty:
            chunks.append(processed)
        print(f"  Chunk {chunk_num}: {len(chunk)} in → {len(processed)} kept")

    df = pd.concat(chunks, ignore_index=True)
    print(f"\n  Total after filter: {len(df)} rows")

    # Add date flags
    df = add_date_flags(df, "listed_date")

    # Explode skills_desc → long table
    skills_long = pd.DataFrame()
    if "skills_desc" in df.columns:
        df["skills_desc"] = df["skills_desc"].astype(str).str.replace(",", ";")
        skills_long = explode_semicolon(
            df,
            id_col=["job_id", "role_category", "listed_date",
                    "post_chatgpt", "period"],
            value_col="skills_desc",
            new_col="skill",
        )
        skills_long = skills_long[skills_long["skill"].str.len() > 1]
        print(f"  Skills long: {len(skills_long)} rows")
        df = df.drop(columns=["skills_desc"])

    # Save full file
    out_main = P["processed"] / "linkedin_clean.parquet"
    df.to_parquet(out_main, index=False)
    print(f"  Saved main  → {out_main}  ({len(df)} rows, {len(df.columns)} cols)")

    # Save tech-only subset — this is what dashboard uses
    df_tech = df[df["is_tech_job"]].copy()
    out_tech = P["processed"] / "linkedin_tech_only.parquet"
    df_tech.to_parquet(out_tech, index=False)
    print(f"  Saved tech  → {out_tech}  ({len(df_tech)} rows)")

    if not skills_long.empty:
        out_long = P["processed"] / "linkedin_skills_long.parquet"
        skills_long.to_parquet(out_long, index=False)
        print(f"  Saved long  → {out_long}  ({len(skills_long)} rows)")

    log_report({
        "source":        "linkedin",
        "rows_in":       rows_in,
        "rows_out":      len(df),
        "rows_tech_only": len(df_tech),
        "notes": (
            "FIXED: expanded TITLE_MAP regexes, is_tech_job flag added, "
            "ai_skill_score uses unique pattern matching. "
            "linkedin_tech_only.parquet = tech/data jobs only."
        ),
    }, P["report"])

    return df, skills_long


if __name__ == "__main__":
    df, skills = clean_linkedin()

    print(f"\nShape: {df.shape}")

    print(f"\nRole category distribution (all jobs):")
    print(df["role_category"].value_counts())

    print(f"\nTech jobs only: {df['is_tech_job'].sum():,} / {len(df):,}")

    print(f"\nRole category distribution (tech only):")
    print(df[df["is_tech_job"]]["role_category"].value_counts())

    print(f"\nai_skill_score (tech jobs):")
    print(df[df["is_tech_job"]]["ai_skill_score"].describe())

    if not skills.empty:
        print(f"\nTop skills:")
        print(skills["skill"].value_counts().head(10))
