"""
agent/context_router.py
------------------------
Decides which context blocks (uploaded dataset, sales, customers,
inventory, documents) are relevant to a question, using plain keyword
matching — no LLM call needed for this step. This keeps the whole
pipeline to exactly one generation (see ai_agent.py's design note), while
still letting the agent draw on multiple data sources.

Also tracks which sources actually contributed context for a given
question, so the agent can cite them in its answer (see ai_agent.py).

Active uploaded dataset: if the user has uploaded a custom CSV via
/api/dataset/upload, its computed summary (tools/generic_analysis.py) is
ALWAYS included — unconditionally, not keyword-gated — because it's
usually the whole reason someone uploaded it: they want to ask about it.
This is what makes "upload any CSV and ask about it" actually work; a
dataset that's profiled but never reaches the agent is profiled for
nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.active_dataset import get_active_dataset_path
from rag.document_store import search_documents
from tools.customer_analysis import customer_summary_text
from tools.generic_analysis import dataset_summary_text
from tools.inventory_analysis import inventory_summary_text
from tools.sales_analysis import sales_summary_text

# Keywords that pull in each optional context block. The built-in demo
# sales data is always included alongside any uploaded dataset — it's
# cheap to compute and keeps the demo questions/buttons working even
# after a custom dataset is active.
#
# Matching uses regex word boundaries (\b) rather than plain substring
# search, so e.g. "contract" doesn't false-positive match inside
# "contractor", and "return" doesn't match inside "returning revenue".
TRIGGERS = {
    "customers": [
        "customer", "customers", "churn", "retention", "buyer", "buyers",
        "client", "clients", "loyal",
    ],
    "inventory": [
        "inventory", "stock", "warehouse", "warehouses", "reorder",
        "restock", "supply",
    ],
    "documents": [
        "policy", "policies", "return", "returns", "refund", "refunds",
        "warranty", "shipping", "delivery", "document", "documents",
        "contract", "contracts", "terms", "guarantee",
    ],
}


@dataclass
class ContextResult:
    """The assembled context text, plus which sources fed into it —
    used to attach citations to the agent's final answer."""

    text: str
    sources: list[str] = field(default_factory=list)


def _matches(question: str, keywords: list[str]) -> bool:
    q = question.lower()
    return any(re.search(rf"\b{re.escape(kw)}\b", q) for kw in keywords)


def build_context(question: str) -> ContextResult:
    """Return the combined, labeled context for a question, along with
    the list of sources that contributed to it (for citations)."""
    blocks: list[str] = []
    sources: list[str] = []

    active_dataset = get_active_dataset_path()
    if active_dataset:
        try:
            summary = dataset_summary_text(active_dataset)
            blocks.append(f"UPLOADED DATASET ({active_dataset.name}):\n{summary}")
            sources.append(active_dataset.name)
        except Exception:
            # If the active dataset became unreadable (deleted, corrupted),
            # silently fall back to the built-in demo data rather than
            # crashing the whole chat request over it.
            pass

    blocks.append("SALES DATA (built-in demo data):\n" + sales_summary_text())
    sources.append("sales.csv")

    if _matches(question, TRIGGERS["customers"]):
        blocks.append("CUSTOMER DATA:\n" + customer_summary_text())
        sources.append("sales.csv (customer view)")

    if _matches(question, TRIGGERS["inventory"]):
        blocks.append("INVENTORY DATA:\n" + inventory_summary_text())
        sources.append("inventory.csv")

    if _matches(question, TRIGGERS["documents"]):
        results = search_documents(question, top_k=3)
        if results:
            doc_text = "\n\n".join(f"[{r['source']}]\n{r['text']}" for r in results)
            blocks.append("RELEVANT COMPANY DOCUMENT EXCERPTS:\n" + doc_text)
            # de-duplicate while preserving order (a doc can supply >1 chunk)
            for r in results:
                if r["source"] not in sources:
                    sources.append(r["source"])

    return ContextResult(text="\n\n".join(blocks), sources=sources)
