"""Tests for tools/inventory_analysis.py and tools/customer_analysis.py."""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from tools.inventory_analysis import analyze_inventory  # noqa: E402
from tools.customer_analysis import analyze_customers  # noqa: E402


@pytest.fixture
def inventory_csv(tmp_path):
    path = tmp_path / "inventory.csv"
    rows = [
        ["product", "warehouse", "stock_level", "reorder_threshold", "unit_cost"],
        ["Laptop Pro", "Berlin", 5, 25, 1000],
        ["Laptop Pro", "Paris", 40, 25, 1000],
        ["Phone X", "Berlin", 60, 30, 500],
    ]
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows(rows)
    return path


def test_total_stock_value(inventory_csv):
    r = analyze_inventory(inventory_csv)
    assert r["total_stock_value"] == 5 * 1000 + 40 * 1000 + 60 * 500


def test_low_stock_detection(inventory_csv):
    r = analyze_inventory(inventory_csv)
    assert len(r["low_stock"]) == 1
    assert r["low_stock"][0]["product"] == "Laptop Pro"
    assert r["low_stock"][0]["warehouse"] == "Berlin"
    assert r["low_stock"][0]["shortfall"] == 20


def test_by_product_and_warehouse(inventory_csv):
    r = analyze_inventory(inventory_csv)
    assert r["by_product"]["Laptop Pro"] == 45
    assert r["by_warehouse"]["Berlin"] == 65


@pytest.fixture
def sales_csv_for_customers(tmp_path):
    path = tmp_path / "sales.csv"
    rows = [
        ["date", "product", "customer", "country", "revenue"],
        ["2026-01-01", "Laptop Pro", "C001", "Germany", "2000"],
        ["2026-01-15", "Phone X", "C002", "France", "1000"],
        ["2026-06-01", "Laptop Pro", "C001", "Germany", "2000"],
    ]
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows(rows)
    return path


def test_top_customers_ranked_by_revenue(sales_csv_for_customers):
    r = analyze_customers(sales_csv_for_customers)
    assert r["total_customers"] == 2
    assert r["top_customers"][0]["customer"] == "C001"
    assert r["top_customers"][0]["revenue"] == 4000.0
    assert r["top_customers"][0]["orders"] == 2


def test_churn_candidate_detected(sales_csv_for_customers):
    r = analyze_customers(sales_csv_for_customers)
    # C002 only ordered in January (first half); C001 ordered in both halves
    assert "C002" in r["churn_candidates"]
    assert "C001" not in r["churn_candidates"]
