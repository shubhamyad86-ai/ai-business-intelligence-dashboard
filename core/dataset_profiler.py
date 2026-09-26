from __future__ import annotations
import json, re
from pathlib import Path
from typing import Any

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")

def _kind(name: str) -> str | None:
    n = _norm(name)
    rules = {
        "date": ["date", "order_date", "quarter", "period", "month", "year"],
        "revenue": ["revenue", "sales", "amount", "net_sales", "turnover"],
        "quantity": ["quantity", "qty", "units", "volume", "deliveries"],
        "inventory": ["inventory", "stock", "on_hand", "ending_inventory", "inventories"],
        "product": ["product", "model", "sku", "item"],
        "customer": ["customer", "client", "account"],
        "country": ["country", "region", "market", "location"],
        "share": ["share", "percentage", "percent", "ratio"],
        "bev": ["bev", "battery_electric"],
        "phev": ["phev", "plug_in_hybrid"],
        "total": ["total", "overall"],
    }
    for k, words in rules.items():
        if any(w in n for w in words):
            return k
    return None

def profile_csv(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    df = pd.read_csv(p)
    columns = []
    for c in df.columns:
        kind = _kind(c)
        dtype = str(df[c].dtype)
        columns.append({
            "name": str(c), "normalized": _norm(c), "kind": kind,
            "dtype": dtype, "nulls": int(df[c].isna().sum()),
            "unique": int(df[c].nunique(dropna=True)),
        })

    kinds = {c["kind"] for c in columns if c["kind"]}
    if {"bev", "phev"} & kinds or "bev" in kinds or "phev" in kinds:
        dataset_type = "electrification"
    elif "inventory" in kinds and ("product" in kinds or "date" in kinds):
        dataset_type = "inventory"
    elif "revenue" in kinds or ("quantity" in kinds and "product" in kinds):
        dataset_type = "sales"
    elif "customer" in kinds:
        dataset_type = "customer"
    else:
        dataset_type = "generic"

    numeric = [str(c) for c in df.select_dtypes(include="number").columns]
    dates = []
    for c in df.columns:
        series = df[c]
        # Only attempt date-parsing on text-like columns. Running this on
        # numeric columns is both noisy (triggers the "could not infer
        # format" warning constantly) and risky (pandas can misparse small
        # integers as epoch timestamps, misdetecting them as dates).
        if not (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)):
            continue
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            parsed = pd.to_datetime(series, errors="coerce")
        if parsed.notna().mean() >= 0.8 and parsed.nunique() > 1:
            dates.append(str(c))

    dashboard = recommend_dashboard(dataset_type, columns, numeric, dates)
    return {
        "filename": p.name,
        "rows": int(len(df)),
        "columns": columns,
        "numeric_columns": numeric,
        "date_columns": dates,
        "dataset_type": dataset_type,
        "dashboard": dashboard,
    }

def recommend_dashboard(dataset_type, columns, numeric, dates):
    names = [c["name"] for c in columns]
    by_kind = {}
    for c in columns:
        if c["kind"]:
            by_kind[c["kind"]] = c["name"]

    if dataset_type == "electrification":
        return {
            "title": "Electrified Vehicle Operations",
            "subtitle": "Electrification mix, deliveries and inventory over time",
            "kpis": [x for x in [
                by_kind.get("electrified"), by_kind.get("share"),
                by_kind.get("bev"), by_kind.get("phev"),
                by_kind.get("total"), by_kind.get("inventory")
            ] if x],
            "charts": [
                {"type":"line","title":"Electrified share over time","x":dates[0] if dates else None,"y":by_kind.get("share")},
                {"type":"line","title":"BEV and PHEV trend","x":dates[0] if dates else None,"y":[by_kind.get("bev"),by_kind.get("phev")]},
                {"type":"line","title":"Deliveries vs inventory","x":dates[0] if dates else None,"y":[by_kind.get("total"),by_kind.get("inventory")]},
            ],
            "questions": [
                "How has electrification changed over time?",
                "Are inventories growing faster than deliveries?",
                "Is BEV adoption accelerating?",
                "What changed in the latest quarter?"
            ],
        }

    if dataset_type == "inventory":
        return {
            "title":"Inventory Operations",
            "subtitle":"Stock levels, replenishment risk and inventory trends",
            "kpis":[by_kind.get("inventory"), by_kind.get("quantity")],
            "charts":[
                {"type":"line","title":"Inventory trend","x":dates[0] if dates else None,"y":by_kind.get("inventory")},
                {"type":"bar","title":"Quantity by product","x":by_kind.get("product"),"y":by_kind.get("quantity")},
            ],
            "questions":["Which products are low in stock?","What inventory risks should we act on?"]
        }

    if dataset_type == "sales":
        return {
            "title":"Sales Performance",
            "subtitle":"Revenue, volume and commercial trends",
            "kpis":[by_kind.get("revenue"),by_kind.get("quantity")],
            "charts":[
                {"type":"line","title":"Revenue trend","x":dates[0] if dates else None,"y":by_kind.get("revenue")},
                {"type":"bar","title":"Revenue by product","x":by_kind.get("product"),"y":by_kind.get("revenue")},
            ],
            "questions":["What is driving revenue?","Which product is performing best?","Why did revenue change?"]
        }

    return {
        "title":"AI Data Overview",
        "subtitle":"Automatically selected metrics and trends",
        "kpis": numeric[:6],
        "charts":[
            {"type":"line","title":"Numeric trend","x":dates[0] if dates else None,"y":numeric[:3]}
        ],
        "questions":["Summarize this dataset.","What are the most important trends?","What anomalies should I investigate?"]
    }

def save_profile(profile: dict[str, Any]) -> None:
    (DATA_DIR / "active_dataset_profile.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
