# =============================================================================
# src/utils_clean.py — Shared Cleaning Helpers
# =============================================================================
# Used by all cleaning scripts. Import with:
#   from utils_clean import coerce_int, coerce_float, log_report, ...
# =============================================================================

from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# TYPE COERCION
# ─────────────────────────────────────────────────────────────────────────────

def coerce_int(series: pd.Series) -> pd.Series:
    """Safe cast to nullable Int64. Non-numeric → NaN."""
    return pd.to_numeric(series, errors="coerce").astype("Int64")


def coerce_float(series: pd.Series) -> pd.Series:
    """Safe cast to float64. Non-numeric → NaN."""
    return pd.to_numeric(series, errors="coerce").astype("float64")


def coerce_datetime(series: pd.Series, fmt: str | None = None) -> pd.Series:
    """Safe cast to datetime64. Bad values → NaT."""
    return pd.to_datetime(series, format=fmt, errors="coerce")


def coerce_unix_ms(series: pd.Series) -> pd.Series:
    """Convert Unix timestamp in milliseconds → datetime (UTC)."""
    return pd.to_datetime(
        pd.to_numeric(series, errors="coerce"), unit="ms", errors="coerce"
    )


# ─────────────────────────────────────────────────────────────────────────────
# STRING HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def clean_str(series: pd.Series) -> pd.Series:
    """Strip whitespace, normalise internal spaces, empty string → NaN."""
    s = series.astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
    return s.replace({"nan": np.nan, "": np.nan, "None": np.nan})


def extract_first_number(series: pd.Series) -> pd.Series:
    """
    Pull the first integer/float from a messy string column.
    e.g. '$37K-$66K (Glassdoor est.)' → 37
         '2085.2'                      → 2085.2
    Returns float64.
    """
    return (
        series.astype(str)
              .str.extract(r"([\d,]+\.?\d*)", expand=False)
              .str.replace(",", "")
              .pipe(coerce_float)
    )


def parse_salary_range(series: pd.Series) -> pd.DataFrame:
    """
    Parse strings like '$37K-$66K (Glassdoor est.)' into three columns:
    salary_min, salary_max, salary_mid (all in full USD, K multiplied).

    Returns a DataFrame with those three columns.
    """
    def _parse_one(val: str):
        if pd.isna(val):
            return np.nan, np.nan, np.nan
        nums = re.findall(r"\$?([\d\.]+)K?", str(val))
        if not nums:
            return np.nan, np.nan, np.nan
        vals = [float(n) * 1000 if "K" in str(val).upper() else float(n)
                for n in nums[:2]]
        lo = vals[0]
        hi = vals[1] if len(vals) > 1 else lo
        return lo, hi, (lo + hi) / 2

    rows = series.apply(_parse_one)
    out = pd.DataFrame(rows.tolist(), columns=["salary_min", "salary_max", "salary_mid"],
                       index=series.index)
    return out.astype("float64")


# ─────────────────────────────────────────────────────────────────────────────
# YEARS-CODE HELPER  (Stack Overflow specific)
# ─────────────────────────────────────────────────────────────────────────────

def parse_years_code(series: pd.Series) -> pd.Series:
    """
    Convert YearsCode strings to numeric:
      'Less than 1 year'  → 0.5
      'More than 50 years'→ 50
      '18'               → 18.0
    """
    mapping = {
        "less than 1 year": 0.5,
        "more than 50 years": 50.0,
    }
    s = series.astype(str).str.strip().str.lower()
    s = s.map(lambda x: mapping.get(x, x))
    return coerce_float(pd.Series(s, index=series.index))


# ─────────────────────────────────────────────────────────────────────────────
# OUTLIER CAPPING
# ─────────────────────────────────────────────────────────────────────────────

def cap_percentile(series: pd.Series, lower: float = 0.01,
                   upper: float = 0.99) -> pd.Series:
    """Winsorise a numeric series at given percentiles."""
    lo = series.quantile(lower)
    hi = series.quantile(upper)
    return series.clip(lower=lo, upper=hi)


# ─────────────────────────────────────────────────────────────────────────────
# SEMICOLON-EXPLODE  (Stack Overflow / LinkedIn skills)
# ─────────────────────────────────────────────────────────────────────────────

def explode_semicolon(df: pd.DataFrame, id_col: str,
                      value_col: str, new_col: str) -> pd.DataFrame:
    """
    Explode a semicolon-separated column into a long table.

    Parameters
    ----------
    df        : source DataFrame
    id_col    : column(s) to keep as identifier (str or list)
    value_col : column containing 'A;B;C' strings
    new_col   : name for the exploded values column

    Returns a long DataFrame: [id_col, new_col]
    """
    id_cols = [id_col] if isinstance(id_col, str) else id_col
    keep = id_cols + [value_col]
    out = (
        df[keep]
        .dropna(subset=[value_col])
        .copy()
    )
    out[new_col] = out[value_col].str.split(";")
    out = out.explode(new_col)
    out[new_col] = out[new_col].str.strip()
    out = out[out[new_col] != ""]
    return out[id_cols + [new_col]].reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# DATE FLAGS
# ─────────────────────────────────────────────────────────────────────────────

CHATGPT_LAUNCH = pd.Timestamp("2022-11-01")   # ChatGPT public release


def add_date_flags(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    """
    Add helper columns to any DataFrame with a datetime column:
      - year        : int
      - quarter     : int (1–4)
      - post_chatgpt: bool (True if date >= Nov 2022)
      - period      : 'pre_chatgpt' | 'post_chatgpt'
    """
    dt = df[date_col]
    df = df.copy()
    df["year"]         = dt.dt.year.astype("Int64")
    df["quarter"]      = dt.dt.quarter.astype("Int64")
    df["post_chatgpt"] = dt >= CHATGPT_LAUNCH
    df["period"]       = np.where(df["post_chatgpt"], "post_chatgpt", "pre_chatgpt")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# COVID FLAG
# ─────────────────────────────────────────────────────────────────────────────

COVID_START = pd.Timestamp("2020-03-01")
COVID_END   = pd.Timestamp("2021-12-31")


def add_covid_flag(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    """Add a bool column `covid_period` for 2020-03 to 2021-12."""
    df = df.copy()
    dt = df[date_col]
    df["covid_period"] = (dt >= COVID_START) & (dt <= COVID_END)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# REPORTING
# ─────────────────────────────────────────────────────────────────────────────

def log_report(report: dict, out_path: str | Path) -> None:
    """
    Append a cleaning report entry to cleaning_report.json.
    report should have keys: source, rows_in, rows_out, notes
    """
    path = Path(out_path)
    existing: list[dict[str, Any]] = []
    if path.exists():
        with open(path) as f:
            existing = json.load(f)

    # Replace existing entry for same source or append
    existing = [e for e in existing if e.get("source") != report.get("source")]
    existing.append(report)

    with open(path, "w") as f:
        json.dump(existing, f, indent=2, default=str)

    print(f"  Logged report for '{report.get('source')}' → {path}")


# ─────────────────────────────────────────────────────────────────────────────
# PATHS  (centralised so all scripts use same dirs)
# ─────────────────────────────────────────────────────────────────────────────

def get_paths(project_root: str | Path | None = None) -> dict:
    root = Path(__file__).parent   # src/ itself, since raw/ and src/ are siblings
    return {
        "root":      root,
        "raw":       root.parent / "raw",
        "processed": root.parent / "processed",
        "report":    root.parent / "processed" / "cleaning_report.json",
    }