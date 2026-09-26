"""
tests/test_dataset_upload_e2e.py
----------------------------------
End-to-end test for the full "upload a CSV, then ask about it" flow —
the exact thing that was broken (dataset got profiled but never reached
chat). This posts a real file to /api/dataset/upload through the actual
FastAPI app, then verifies agent.context_router picks it up, without
needing a live Ollama server (the LLM call itself is out of scope here;
what's under test is that the RIGHT DATA reaches the prompt).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import backend.main as main  # noqa: E402
from core.active_dataset import clear_active_dataset  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_active_dataset():
    """Never let one test's uploaded dataset leak into another test."""
    clear_active_dataset()
    yield
    clear_active_dataset()


@pytest.fixture
def quarterly_csv_bytes():
    return (
        b"Quarter,BEV,PHEV,Total\n"
        b"2019-Q1,8694,23461,32155\n"
        b"2019-Q2,9485,25593,35078\n"
        b"2020-Q1,9799,27000,36799\n"
        b"2020-Q2,10690,28000,38690\n"
    )


def test_upload_endpoint_returns_real_stats(quarterly_csv_bytes):
    client = TestClient(main.app)
    resp = client.post(
        "/api/dataset/upload",
        files={"file": ("quarterly.csv", quarterly_csv_bytes, "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"] == 4
    assert "BEV" in body["stats"]["numeric_summary"]
    assert "BEV" in body["summary_text"]


def test_active_dataset_endpoint_reflects_upload(quarterly_csv_bytes):
    client = TestClient(main.app)
    client.post("/api/dataset/upload", files={"file": ("q.csv", quarterly_csv_bytes, "text/csv")})
    resp = client.get("/api/dataset/active")
    assert resp.status_code == 200
    assert resp.json()["active"] is True


def test_uploaded_dataset_reaches_chat_context(quarterly_csv_bytes):
    """The critical regression test: after upload, a question must be
    grounded in the uploaded data, not just the built-in demo sales data."""
    client = TestClient(main.app)
    client.post("/api/dataset/upload", files={"file": ("q.csv", quarterly_csv_bytes, "text/csv")})

    from agent.context_router import build_context

    result = build_context("What is the BEV trend?")
    assert any("q.csv" in s or "q_" in s for s in result.sources) or "BEV" in result.text
    assert "8694" in result.text or "10690" in result.text


def test_deactivate_falls_back_to_demo_data(quarterly_csv_bytes):
    client = TestClient(main.app)
    client.post("/api/dataset/upload", files={"file": ("q.csv", quarterly_csv_bytes, "text/csv")})
    resp = client.delete("/api/dataset/active")
    assert resp.status_code == 200
    assert resp.json()["active"] is False

    from agent.context_router import build_context

    result = build_context("Why did revenue drop?")
    assert "UPLOADED DATASET" not in result.text


def test_rejects_non_csv_upload():
    client = TestClient(main.app)
    resp = client.post(
        "/api/dataset/upload",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )
    assert resp.status_code == 400


def test_rejects_empty_csv():
    client = TestClient(main.app)
    resp = client.post(
        "/api/dataset/upload",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert resp.status_code == 400
