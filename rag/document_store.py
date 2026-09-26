"""
rag/document_store.py
----------------------
A minimal, local RAG (retrieval-augmented generation) layer over company
documents (data/documents/*.md, *.txt). No vector database needed at this
scale — documents are chunked, embedded once, cached in memory, and
searched with cosine similarity.

Embeddings come from Ollama's embedding endpoint (default model:
"nomic-embed-text" — pull it with `ollama pull nomic-embed-text`). If that
model isn't available, retrieval automatically falls back to a simple
keyword-overlap score, so the feature still works without the extra pull —
just less precisely.

Add more documents by dropping .md or .txt files into data/documents/.
"""

from __future__ import annotations

import math
from dotenv import load_dotenv
load_dotenv()
import os
import re
from pathlib import Path
from typing import Optional

import ollama

DOCS_DIR = Path(__file__).resolve().parent.parent / "data" / "documents"
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
EMBED_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

CHUNK_SIZE_CHARS = 700
CHUNK_OVERLAP_CHARS = 100

_client = ollama.Client(host=EMBED_HOST, timeout=120)

# In-memory cache: list of {"source": str, "text": str, "embedding": list[float] | None}
_INDEX: Optional[list[dict]] = None
_EMBEDDINGS_AVAILABLE: Optional[bool] = None


def _chunk_text(text: str, size: int = CHUNK_SIZE_CHARS, overlap: int = CHUNK_OVERLAP_CHARS) -> list[str]:
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end].strip())
        start = end - overlap
    return [c for c in chunks if c]


def _load_documents() -> list[dict]:
    chunks = []
    if not DOCS_DIR.exists():
        return chunks
    for path in sorted(DOCS_DIR.glob("*")):
        if path.suffix.lower() not in (".md", ".txt"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for chunk in _chunk_text(text):
            chunks.append({"source": path.name, "text": chunk, "embedding": None})
    return chunks


def _try_embed(texts: list[str]) -> Optional[list[list[float]]]:
    try:
        result = _client.embed(model=EMBED_MODEL, input=texts)
        return result["embeddings"]
    except Exception:
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _keyword_score(query: str, text: str) -> float:
    """Fallback scorer when embeddings aren't available: fraction of query
    words that appear in the chunk, case-insensitive."""
    q_words = set(re.findall(r"[a-zA-Z]{3,}", query.lower()))
    if not q_words:
        return 0.0
    t_lower = text.lower()
    hits = sum(1 for w in q_words if w in t_lower)
    return hits / len(q_words)


def _ensure_index() -> None:
    global _INDEX, _EMBEDDINGS_AVAILABLE
    if _INDEX is not None:
        return
    _INDEX = _load_documents()
    if not _INDEX:
        _EMBEDDINGS_AVAILABLE = False
        return

    embeddings = _try_embed([c["text"] for c in _INDEX])
    if embeddings and len(embeddings) == len(_INDEX):
        for chunk, emb in zip(_INDEX, embeddings):
            chunk["embedding"] = emb
        _EMBEDDINGS_AVAILABLE = True
    else:
        _EMBEDDINGS_AVAILABLE = False


def search_documents(query: str, top_k: int = 3) -> list[dict]:
    """Return the top_k most relevant chunks as [{source, text, score}]."""
    _ensure_index()
    if not _INDEX:
        return []

    if _EMBEDDINGS_AVAILABLE:
        query_emb = _try_embed([query])
        if query_emb:
            q = query_emb[0]
            scored = [
                {"source": c["source"], "text": c["text"], "score": _cosine(q, c["embedding"])}
                for c in _INDEX
            ]
            scored.sort(key=lambda x: x["score"], reverse=True)
            return scored[:top_k]

    # Fallback: keyword overlap
    scored = [
        {"source": c["source"], "text": c["text"], "score": _keyword_score(query, c["text"])}
        for c in _INDEX
    ]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return [s for s in scored[:top_k] if s["score"] > 0]


def documents_context_text(query: str, top_k: int = 3) -> str:
    """Formatted text block ready to inject into the LLM prompt."""
    results = search_documents(query, top_k=top_k)
    if not results:
        return ""
    parts = [f"[{r['source']}]\n{r['text']}" for r in results]
    return "\n\n".join(parts)


def reset_index_cache() -> None:
    """Call after adding/removing documents so the next search re-reads disk."""
    global _INDEX, _EMBEDDINGS_AVAILABLE
    _INDEX = None
    _EMBEDDINGS_AVAILABLE = None


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "What is the return window?"
    for r in search_documents(q):
        print(f"[{r['score']:.3f}] {r['source']}: {r['text'][:120]}...")
