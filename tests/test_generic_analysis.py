"""Tests for tools/generic_analysis.py — must work on arbitrary CSV shapes,
not just the fixed demo sales data. Includes a regression test built from
a real dataset (BMW electrified-vehicle quarterly data) that originally
exposed a false-positive date-detection bug."""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from tools.generic_analysis import analyze_dataset, dataset_summary_text  # noqa: E402


@pytest.fixture
def quarterly_csv(tmp_path):
    """Mirrors the real BMW dataset's shape: a quarter-period column plus
    several numeric columns, one row per period."""
    path = tmp_path / "quarterly.csv"
    rows = [
        ["Quarter", "BEV", "PHEV", "Total"],
        ["2019-Q1", "8694", "23461", "32155"],
        ["2019-Q2", "9485", "25593", "35078"],
        ["2020-Q1", "9799", "27000", "36799"],
        ["2020-Q2", "10690", "28000", "38690"],
    ]
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows(rows)
    return path


@pytest.fixture
def categorical_csv(tmp_path):
    """A transactional shape: repeated category values, no time column."""
    path = tmp_path / "transactions.csv"
    rows = [
        ["store", "product", "units_sold", "revenue"],
        ["Store A", "Widget", "120", "2400"],
        ["Store B", "Widget", "80", "1600"],
        ["Store A", "Gadget", "60", "3000"],
        ["Store C", "Gadget", "40", "2000"],
    ]
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows(rows)
    return path


def test_quarter_column_detected_as_time(quarterly_csv):
    result = analyze_dataset(quarterly_csv)
    assert result["columns"]["datetime"] == ["Quarter"]
    assert result["date_range"]["start"] == "2019-01-01"


def test_numeric_columns_not_misdetected_as_dates(categorical_csv):
    """Regression test: a plain integer column like units_sold must never
    be mistaken for a date column (pandas can misparse small ints as
    epoch timestamps)."""
    result = analyze_dataset(categorical_csv)
    assert result["columns"]["datetime"] == []
    assert "units_sold" in result["columns"]["numeric"]


def test_trend_stats_computed_correctly(quarterly_csv):
    result = analyze_dataset(quarterly_csv)
    bev = result["numeric_summary"]["BEV"]
    assert bev["first"] == 8694.0
    assert bev["last"] == 10690.0
    assert bev["min"] == 8694.0
    assert bev["max"] == 10690.0
    # (10690 - 9799) / 9799 * 100
    assert bev["latest_change_pct"] == pytest.approx(9.1, abs=0.1)


def test_categorical_grouping_and_totals(categorical_csv):
    result = analyze_dataset(categorical_csv)
    stores = result["categorical_summary"]["store"]
    top_by_units = {i["value"]: i["total"] for i in stores["top_by_units_sold"]}
    assert top_by_units["Store A"] == 180.0  # 120 + 60
    assert top_by_units["Store B"] == 80.0
    assert top_by_units["Store C"] == 40.0


def test_summary_text_mentions_every_numeric_column(quarterly_csv):
    text = dataset_summary_text(quarterly_csv)
    assert "BEV" in text
    assert "PHEV" in text
    assert "Total" in text


def test_summary_text_is_generic_no_hardcoded_sales_language(categorical_csv):
    text = dataset_summary_text(categorical_csv)
    # should not assume "revenue" or "customer" language belongs to every dataset
    assert "Store A" in text
    assert "Widget" in text or "Gadget" in text


def test_empty_csv_raises(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("col1,col2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        analyze_dataset(path)


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        analyze_dataset(tmp_path / "does_not_exist.csv")
