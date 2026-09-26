"""
tests/test_rag_retrieval.py
-----------------------------
Dedicated tests for the RAG layer (rag/document_store.py), independent of
the LLM. These exercise chunking, indexing, and retrieval against a real
temp filesystem of documents — with embeddings unavailable (no Ollama in
CI), so they specifically verify the keyword-fallback search path that
guarantees RAG still works out of the box.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from rag import document_store  # noqa: E402


@pytest.fixture
def temp_docs(tmp_path, monkeypatch):
    """Point the document store at a small, controlled set of docs and
    reset its in-memory cache before and after each test."""
    docs_dir = tmp_path / "documents"
    docs_dir.mkdir()

    (docs_dir / "returns.md").write_text(
        "# Returns Policy\n\n"
        "Customers may return any item within 30 days of delivery for a full refund. "
        "Damaged items can be reported within 48 hours for a replacement.",
        encoding="utf-8",
    )
    (docs_dir / "shipping.md").write_text(
        "# Shipping Policy\n\n"
        "Standard shipping takes 3-5 business days. Express shipping takes 1-2 business days "
        "and costs extra.",
        encoding="utf-8",
    )
    (docs_dir / "notes.txt").write_text(
        "Internal note: warehouse restock happens every Monday morning.",
        encoding="utf-8",
    )

    monkeypatch.setattr(document_store, "DOCS_DIR", docs_dir)
    document_store.reset_index_cache()

    # Force the keyword-fallback path deterministically: no live Ollama in
    # tests, so embeddings should naturally fail, but we pin it explicitly
    # so this test doesn't depend on network availability either way.
    monkeypatch.setattr(document_store, "_try_embed", lambda texts: None)

    yield docs_dir

    document_store.reset_index_cache()


def test_loads_all_documents_in_folder(temp_docs):
    document_store._ensure_index()
    sources = {c["source"] for c in document_store._INDEX}
    assert sources == {"returns.md", "shipping.md", "notes.txt"}


def test_search_finds_relevant_chunk_by_keyword(temp_docs):
    results = document_store.search_documents("What is the return window for damaged items?")
    assert results, "expected at least one match"
    assert results[0]["source"] == "returns.md"
    assert "48 hours" in results[0]["text"] or "30 days" in results[0]["text"]


def test_search_ranks_best_match_first(temp_docs):
    results = document_store.search_documents("express shipping delivery time")
    assert results[0]["source"] == "shipping.md"


def test_search_returns_nothing_for_unrelated_query(temp_docs):
    results = document_store.search_documents("quantum physics unicorn")
    assert results == []


def test_documents_context_text_formats_with_source_tags(temp_docs):
    text = document_store.documents_context_text("return window damaged items")
    assert "[returns.md]" in text


def test_no_documents_folder_returns_empty(tmp_path, monkeypatch):
    empty_dir = tmp_path / "no_such_dir"
    monkeypatch.setattr(document_store, "DOCS_DIR", empty_dir)
    document_store.reset_index_cache()
    assert document_store.search_documents("anything") == []
    document_store.reset_index_cache()
