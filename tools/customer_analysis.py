"""
customer_analysis.py
----------------------
Derives customer-level insights from the same sales data used by
sales_analysis.py: top spenders, order counts, and simple churn
detection (customers active in the first half of the data but silent
in the second half).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from tools.sales_analysis import load_sales


def analyze_customers(path: Optional[Path] = None, top_n: int = 5) -> dict:
    """
    Returns:
      - total_customers: distinct customer count
      - top_customers: [{customer, revenue, orders}] sorted by revenue desc
      - churn_candidates: customers who ordered in the first half of the
        date range but not the second half — a simple, explainable proxy
        for "stopped buying," not a prediction.
    """
    df = load_sales(path)
    if df.empty:
        return {"total_customers": 0, "top_customers": [], "churn_candidates": []}

    grouped = df.groupby("customer").agg(
        revenue=("revenue", "sum"), orders=("revenue", "count")
    ).reset_index()
    grouped = grouped.sort_values("revenue", ascending=False)

    top_customers = [
        {"customer": r["customer"], "revenue": round(float(r["revenue"]), 2), "orders": int(r["orders"])}
        for _, r in grouped.head(top_n).iterrows()
    ]

    min_date, max_date = df["date"].min(), df["date"].max()
    midpoint = min_date + (max_date - min_date) / 2

    first_half_customers = set(df[df["date"] <= midpoint]["customer"])
    second_half_customers = set(df[df["date"] > midpoint]["customer"])
    churned = sorted(first_half_customers - second_half_customers)

    return {
        "total_customers": int(df["customer"].nunique()),
        "top_customers": top_customers,
        "churn_candidates": churned[:15],  # cap the list to keep it readable
    }


def customer_summary_text(path: Optional[Path] = None) -> str:
    r = analyze_customers(path)
    lines = [f"Total distinct customers: {r['total_customers']}."]
    if r["top_customers"]:
        top = ", ".join(f"{c['customer']}=€{c['revenue']:,.2f} ({c['orders']} orders)" for c in r["top_customers"])
        lines.append(f"Top customers by revenue: {top}")
    if r["churn_candidates"]:
        lines.append(
            f"Customers who ordered in the first half of the data but not since "
            f"(possible churn, {len(r['churn_candidates'])} total): "
            + ", ".join(r["churn_candidates"][:10])
            + (" …" if len(r["churn_candidates"]) > 10 else "")
        )
    else:
        lines.append("No customers show a first-half-only ordering pattern.")
    return "\n".join(lines)


if __name__ == "__main__":
    import json
    print(json.dumps(analyze_customers(), indent=2, ensure_ascii=False))
