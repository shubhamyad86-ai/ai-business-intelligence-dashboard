"""
tools/generic_analysis.py
---------------------------
A dataset-agnostic analysis engine: given ANY CSV — regardless of column
names or shape — this computes real, deterministic statistics the agent
can ground answers in, the same way sales_analysis.py does for the fixed
demo sales data.

Two shapes are handled automatically:

1. Time-series-like data (one row per time period, e.g. a "Quarter" or
   "Date" column with mostly-unique values): report each numeric column's
   trend — first value, latest value, overall % change, and the most
   recent period-over-period % change.

2. Categorical/transactional data (many rows sharing repeated category
   values, e.g. a "Product" or "Region" column): report each numeric
   column's total, and the top categories by that numeric column's sum.

Both checks run independently and either, both, or neither can apply to
a given file — the summary includes whatever is actually present.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Any

import pandas as pd

TOP_N_CATEGORIES = 5
MAX_NUMERIC_COLUMNS_REPORTED = 8  # keeps very wide datasets' summaries short and fast to generate


def load_generic_dataset(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found at {path}")
    df = pd.read_csv(path)
    if df.empty:
        raise ValueError("The CSV has no rows.")
    return df


def _best_datetime_column(df: pd.DataFrame) -> tuple[str | None, pd.Series | None]:
    """Find the column most likely to represent time. Handles normal dates
    AND period-style strings like "2019-Q1" (quarters), which pandas'
    plain to_datetime can't parse but are extremely common in business data."""
    best_col, best_series, best_score = None, None, 0.0

    quarter_pattern = re.compile(r"^\s*(\d{4})[-\s]?Q([1-4])\s*$", re.IGNORECASE)

    for col in df.columns:
        series = df[col]
        is_textlike = pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)

        # Try quarter-style strings first (e.g. "2019-Q1") since pandas can't parse these directly.
        if is_textlike:
            matches = series.astype(str).str.match(quarter_pattern)
            if matches.mean() >= 0.8:
                parsed = series.astype(str).apply(
                    lambda v: pd.Period(f"{v[:4]}Q{v[-1]}", freq="Q").start_time
                    if quarter_pattern.match(v)
                    else pd.NaT
                )
                score = matches.mean()
                if score > best_score:
                    best_col, best_series, best_score = col, parsed, score
                continue

        # Otherwise try pandas' general date parser — but only on
        # text/object columns. Running this on numeric columns is a trap:
        # pandas will happily "parse" small integers as epoch timestamps
        # (e.g. treating a units-sold column as nanoseconds since 1970),
        # producing a false-positive date column.
        if not is_textlike:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            parsed = pd.to_datetime(series, errors="coerce")
        valid_frac = parsed.notna().mean()
        uniqueness = parsed.nunique() / max(len(parsed), 1)
        score = valid_frac * uniqueness
        if valid_frac >= 0.8 and score > best_score:
            best_col, best_series, best_score = col, parsed, score

    return best_col, best_series


def classify_columns(df: pd.DataFrame, datetime_col: str | None) -> dict[str, list[str]]:
    numeric_cols = [c for c in df.select_dtypes(include="number").columns if c != datetime_col]
    remaining = [c for c in df.columns if c != datetime_col and c not in numeric_cols]

    categorical_cols, id_like_cols = [], []
    for col in remaining:
        nunique = df[col].nunique(dropna=True)
        if len(df) > 0 and nunique / len(df) > 0.9 and nunique > 20:
            id_like_cols.append(col)  # looks like a free-text/ID column, not a useful grouping key
        else:
            categorical_cols.append(col)

    return {
        "datetime": [datetime_col] if datetime_col else [],
        "numeric": numeric_cols,
        "categorical": categorical_cols,
        "id_like": id_like_cols,
    }


def analyze_dataset(path: str | Path) -> dict[str, Any]:
    df = load_generic_dataset(path)
    datetime_col, datetime_series = _best_datetime_column(df)
    columns = classify_columns(df, datetime_col)

    result: dict[str, Any] = {
        "filename": Path(path).name,
        "rows": int(len(df)),
        "columns": {k: v for k, v in columns.items()},
        "date_range": None,
        "numeric_summary": {},
        "categorical_summary": {},
    }

    # --- Time-series view: sort by time, report trend per numeric column ---
    if datetime_col:
        order = datetime_series.argsort()
        df_sorted = df.iloc[order].reset_index(drop=True)
        valid_dates = datetime_series.iloc[order].reset_index(drop=True)
        result["date_range"] = {
            "column": datetime_col,
            "start": str(valid_dates.iloc[0].date()) if pd.notna(valid_dates.iloc[0]) else None,
            "end": str(valid_dates.iloc[-1].date()) if pd.notna(valid_dates.iloc[-1]) else None,
        }

        for col in columns["numeric"][:MAX_NUMERIC_COLUMNS_REPORTED]:
            series = df_sorted[col].dropna()
            if series.empty:
                continue
            first_val, last_val = float(series.iloc[0]), float(series.iloc[-1])
            change_pct = round((last_val - first_val) / first_val * 100, 1) if first_val else None

            latest_change_pct = None
            if len(series) >= 2:
                prev_val = float(series.iloc[-2])
                latest_change_pct = round((last_val - prev_val) / prev_val * 100, 1) if prev_val else None

            result["numeric_summary"][col] = {
                "sum": round(float(series.sum()), 2),
                "mean": round(float(series.mean()), 2),
                "min": round(float(series.min()), 2),
                "max": round(float(series.max()), 2),
                "first": round(first_val, 2),
                "last": round(last_val, 2),
                "change_pct_over_period": change_pct,
                "latest_change_pct": latest_change_pct,
            }
    else:
        # No usable time column: just report overall stats per numeric column.
        for col in columns["numeric"][:MAX_NUMERIC_COLUMNS_REPORTED]:
            series = df[col].dropna()
            if series.empty:
                continue
            result["numeric_summary"][col] = {
                "sum": round(float(series.sum()), 2),
                "mean": round(float(series.mean()), 2),
                "min": round(float(series.min()), 2),
                "max": round(float(series.max()), 2),
            }

    # --- Categorical view: top categories by count, and by each numeric column's sum ---
    for cat_col in columns["categorical"]:
        top_by_count = df[cat_col].value_counts().head(TOP_N_CATEGORIES)
        entry: dict[str, Any] = {
            "top_by_count": [{"value": str(k), "count": int(v)} for k, v in top_by_count.items()]
        }
        if columns["numeric"]:
            num_col = columns["numeric"][0]  # most informative numeric column, first one
            grouped = df.groupby(cat_col)[num_col].sum().sort_values(ascending=False).head(TOP_N_CATEGORIES)
            entry["top_by_" + num_col] = [{"value": str(k), "total": round(float(v), 2)} for k, v in grouped.items()]
        result["categorical_summary"][cat_col] = entry

    return result


def dataset_summary_text(path: str | Path) -> str:
    """Human-readable summary the agent hands to the LLM as grounding —
    same role as sales_summary_text() but works for any CSV shape."""
    r = analyze_dataset(path)
    lines = [f"Dataset: {r['filename']} ({r['rows']} rows)."]

    if r["date_range"]:
        lines.append(
            f"Time column: {r['date_range']['column']}, spanning {r['date_range']['start']} to {r['date_range']['end']}."
        )

    for col, stats in r["numeric_summary"].items():
        if "first" in stats:
            piece = (
                f"{col}: latest={stats['last']}, started at {stats['first']} "
                f"({stats['change_pct_over_period']}% change over the full period"
            )
            if stats["latest_change_pct"] is not None:
                piece += f", {stats['latest_change_pct']}% vs the previous period"
            piece += f"). Range: {stats['min']}–{stats['max']}, average {stats['mean']}."
        else:
            piece = f"{col}: total={stats['sum']}, average={stats['mean']}, range {stats['min']}–{stats['max']}."
        lines.append(piece)

    for col, entry in r["categorical_summary"].items():
        top_count = ", ".join(f"{c['value']} ({c['count']})" for c in entry["top_by_count"])
        lines.append(f"Top {col} by frequency: {top_count}.")
        for key, items in entry.items():
            if key.startswith("top_by_") and key != "top_by_count":
                num_col = key.removeprefix("top_by_")
                top_sum = ", ".join(f"{i['value']}={i['total']}" for i in items)
                lines.append(f"Top {col} by total {num_col}: {top_sum}.")

    return "\n".join(lines)


if __name__ == "__main__":
    import json
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else None
    if not target:
        print("Usage: python -m tools.generic_analysis <path-to-csv>")
        sys.exit(1)
    print(json.dumps(analyze_dataset(target), indent=2, default=str))
    print()
    print(dataset_summary_text(target))
