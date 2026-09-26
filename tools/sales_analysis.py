"""
sales_analysis.py
------------------
Core analysis tool used by the AI agent. Loads the company's sales data
and computes real, verifiable numbers (never model guesswork).

This module has no dependency on the LLM or the agent — it can be
imported and tested on its own, and it's also what the agent calls
under the hood when a user asks a sales question.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Optional

import pandas as pd

DEFAULT_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "sales.csv"


def load_sales(path: Optional[Path] = None) -> pd.DataFrame:
    """Load and lightly validate the sales CSV."""
    path = Path(path) if path else DEFAULT_DATA_PATH
    if not path.exists():
        raise FileNotFoundError(f"Sales data not found at {path}")

    df = pd.read_csv(path, parse_dates=["date"])
    required = {"date", "product", "customer", "country", "revenue"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"sales.csv is missing required columns: {missing}")

    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce")
    df = df.dropna(subset=["revenue"])
    df["month"] = df["date"].dt.strftime("%Y-%m")
    return df


def analyze_sales(path: Optional[Path] = None) -> dict:
    """
    Compute the full set of sales metrics used by the agent and dashboard.

    Returns a JSON-serializable dict with:
      - total_revenue, total_orders
      - monthly_revenue: {month: revenue}
      - product_revenue: {product: revenue}
      - country_revenue: {country: revenue}
      - month_over_month: [{month, revenue, change_pct}]
      - biggest_declining_product: {name, change_pct} | None
      - biggest_declining_country: {name, change_pct} | None
      - top_product, top_country
    """
    df = load_sales(path)

    monthly_revenue = df.groupby("month")["revenue"].sum().round(2).to_dict()
    product_revenue = df.groupby("product")["revenue"].sum().round(2).to_dict()
    country_revenue = df.groupby("country")["revenue"].sum().round(2).to_dict()

    total_revenue = round(float(df["revenue"].sum()), 2)
    total_orders = int(len(df))

    months_sorted = sorted(monthly_revenue.keys())
    mom = []
    prev = None
    for m in months_sorted:
        rev = monthly_revenue[m]
        change_pct = None if prev is None or prev == 0 else round((rev - prev) / prev * 100, 1)
        mom.append({"month": m, "revenue": round(rev, 2), "change_pct": change_pct})
        prev = rev

    def biggest_decline(dimension: str) -> Optional[dict]:
        """Find the (product or country) with the steepest revenue drop
        between the most recent two months present in the data."""
        if len(months_sorted) < 2:
            return None
        last_month, prev_month = months_sorted[-1], months_sorted[-2]
        cur = df[df["month"] == last_month].groupby(dimension)["revenue"].sum()
        prv = df[df["month"] == prev_month].groupby(dimension)["revenue"].sum()
        worst_name, worst_pct = None, 0.0
        for name in prv.index:
            prev_val = prv.get(name, 0.0)
            cur_val = cur.get(name, 0.0)
            if prev_val <= 0:
                continue
            pct = (cur_val - prev_val) / prev_val * 100
            if pct < worst_pct:
                worst_pct, worst_name = pct, name
        if worst_name is None:
            return None
        return {"name": worst_name, "change_pct": round(worst_pct, 1)}

    result = {
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "monthly_revenue": {k: round(v, 2) for k, v in monthly_revenue.items()},
        "product_revenue": {k: round(v, 2) for k, v in product_revenue.items()},
        "country_revenue": {k: round(v, 2) for k, v in country_revenue.items()},
        "month_over_month": mom,
        "biggest_declining_product": biggest_decline("product"),
        "biggest_declining_country": biggest_decline("country"),
        "top_product": max(product_revenue, key=product_revenue.get) if product_revenue else None,
        "top_country": max(country_revenue, key=country_revenue.get) if country_revenue else None,
    }
    return result


def sales_summary_text(path: Optional[Path] = None) -> str:
    """A short, human-readable summary the agent can hand to the LLM as
    grounding context, so the model explains real numbers instead of
    inventing them."""
    r = analyze_sales(path)
    lines = [
        f"Total revenue: €{r['total_revenue']:,.2f} across {r['total_orders']} orders.",
        "Monthly revenue: " + ", ".join(f"{m}=€{v:,.2f}" for m, v in sorted(r["monthly_revenue"].items())),
        "Revenue by product: " + ", ".join(f"{p}=€{v:,.2f}" for p, v in r["product_revenue"].items()),
        "Revenue by country: " + ", ".join(f"{c}=€{v:,.2f}" for c, v in r["country_revenue"].items()),
    ]
    if r["biggest_declining_product"]:
        d = r["biggest_declining_product"]
        lines.append(f"Steepest product decline (last month vs prior): {d['name']} ({d['change_pct']}%)")
    if r["biggest_declining_country"]:
        d = r["biggest_declining_country"]
        lines.append(f"Steepest country decline (last month vs prior): {d['name']} ({d['change_pct']}%)")
    return "\n".join(lines)


if __name__ == "__main__":
    import json
    print(json.dumps(analyze_sales(), indent=2, ensure_ascii=False))
