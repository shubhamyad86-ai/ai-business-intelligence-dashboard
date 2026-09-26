"""
inventory_analysis.py
----------------------
Analyzes stock levels against reorder thresholds. Same philosophy as
sales_analysis.py: pure, deterministic, model-independent, and unit-tested.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

DEFAULT_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "inventory.csv"


def load_inventory(path: Optional[Path] = None) -> pd.DataFrame:
    path = Path(path) if path else DEFAULT_DATA_PATH
    if not path.exists():
        raise FileNotFoundError(f"Inventory data not found at {path}")

    df = pd.read_csv(path)
    required = {"product", "warehouse", "stock_level", "reorder_threshold", "unit_cost"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"inventory.csv is missing required columns: {missing}")

    for col in ("stock_level", "reorder_threshold", "unit_cost"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["stock_level", "reorder_threshold", "unit_cost"])


def analyze_inventory(path: Optional[Path] = None) -> dict:
    """
    Returns:
      - total_stock_value: sum(stock_level * unit_cost)
      - by_product: {product: total_units}
      - by_warehouse: {warehouse: total_units}
      - low_stock: [{product, warehouse, stock_level, reorder_threshold, shortfall}]
        for every row below its reorder threshold, worst shortfall first
    """
    df = load_inventory(path)

    df["stock_value"] = df["stock_level"] * df["unit_cost"]
    total_stock_value = round(float(df["stock_value"].sum()), 2)

    by_product = df.groupby("product")["stock_level"].sum().astype(int).to_dict()
    by_warehouse = df.groupby("warehouse")["stock_level"].sum().astype(int).to_dict()

    low = df[df["stock_level"] < df["reorder_threshold"]].copy()
    low["shortfall"] = low["reorder_threshold"] - low["stock_level"]
    low = low.sort_values("shortfall", ascending=False)

    low_stock = [
        {
            "product": r["product"],
            "warehouse": r["warehouse"],
            "stock_level": int(r["stock_level"]),
            "reorder_threshold": int(r["reorder_threshold"]),
            "shortfall": int(r["shortfall"]),
        }
        for _, r in low.iterrows()
    ]

    return {
        "total_stock_value": total_stock_value,
        "by_product": {k: int(v) for k, v in by_product.items()},
        "by_warehouse": {k: int(v) for k, v in by_warehouse.items()},
        "low_stock": low_stock,
    }


def inventory_summary_text(path: Optional[Path] = None) -> str:
    r = analyze_inventory(path)
    lines = [
        f"Total inventory value: €{r['total_stock_value']:,.2f}.",
        "Units by product: " + ", ".join(f"{p}={v}" for p, v in r["by_product"].items()),
        "Units by warehouse: " + ", ".join(f"{w}={v}" for w, v in r["by_warehouse"].items()),
    ]
    if r["low_stock"]:
        items = "; ".join(
            f"{i['product']} at {i['warehouse']} ({i['stock_level']}/{i['reorder_threshold']}, "
            f"short by {i['shortfall']})"
            for i in r["low_stock"]
        )
        lines.append(f"Below reorder threshold: {items}")
    else:
        lines.append("No products are below their reorder threshold.")
    return "\n".join(lines)


if __name__ == "__main__":
    import json
    print(json.dumps(analyze_inventory(), indent=2))
