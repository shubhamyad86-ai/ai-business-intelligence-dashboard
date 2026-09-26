"""
Tests for tools/sales_analysis.py — the one part of the system that must
be correct with no ambiguity, since the LLM's answers are only as
trustworthy as these numbers.

Run with:  pytest tests/
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from tools.sales_analysis import analyze_sales, load_sales  # noqa: E402


@pytest.fixture
def sample_csv(tmp_path):
    path = tmp_path / "sales.csv"
    rows = [
        ["date", "product", "customer", "country", "revenue"],
        ["2026-01-05", "Laptop Pro", "C001", "Germany", "2000"],
        ["2026-01-12", "Phone X", "C002", "France", "1000"],
        ["2026-02-03", "Laptop Pro", "C003", "Germany", "1000"],  # decline vs Jan
        ["2026-02-20", "Phone X", "C004", "France", "1200"],
    ]
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows(rows)
    return path


def test_load_sales_parses_dates_and_month(sample_csv):
    df = load_sales(sample_csv)
    assert len(df) == 4
    assert "month" in df.columns
    assert set(df["month"]) == {"2026-01", "2026-02"}


def test_totals(sample_csv):
    result = analyze_sales(sample_csv)
    assert result["total_revenue"] == 5200.0
    assert result["total_orders"] == 4


def test_monthly_and_product_breakdown(sample_csv):
    result = analyze_sales(sample_csv)
    assert result["monthly_revenue"]["2026-01"] == 3000.0
    assert result["monthly_revenue"]["2026-02"] == 2200.0
    assert result["product_revenue"]["Laptop Pro"] == 3000.0
    assert result["product_revenue"]["Phone X"] == 2200.0


def test_top_product_and_country(sample_csv):
    result = analyze_sales(sample_csv)
    assert result["top_product"] == "Laptop Pro"
    assert result["top_country"] == "Germany"


def test_biggest_declining_product_detected(sample_csv):
    result = analyze_sales(sample_csv)
    decline = result["biggest_declining_product"]
    assert decline is not None
    assert decline["name"] == "Laptop Pro"
    assert decline["change_pct"] == -50.0


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        analyze_sales(tmp_path / "does_not_exist.csv")
