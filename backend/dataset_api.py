"""
backend/dataset_api.py
------------------------
Upload endpoint for arbitrary CSV datasets. This is what actually makes
"upload any CSV and ask questions about it" work:

  1. Save the uploaded file.
  2. Run it through tools/generic_analysis.py to get REAL computed stats
     (not just a schema guess) — this is what grounds the agent's answers.
  3. Mark it as the "active dataset" (core/active_dataset.py), which
     agent/context_router.py checks on every chat request.

Without step 3, an uploaded dataset would be profiled but never actually
reach the chat agent — which was the original bug (BMW dataset upload
"worked" but chat never knew it existed).
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from core.active_dataset import UPLOADS_DIR, clear_active_dataset, get_active_dataset_path, set_active_dataset
from core.dataset_profiler import profile_csv
from tools.generic_analysis import analyze_dataset, dataset_summary_text

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dataset", tags=["dataset"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB — generous for a CSV, protects against accidental huge files


def _safe_filename(name: str) -> str:
    name = Path(name).name  # strip any directory components
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return name or "dataset.csv"


@router.get("/active")
def get_active():
    """What dataset (if any) the chat agent is currently grounding
    document/data questions in, beyond the built-in demo data."""
    path = get_active_dataset_path()
    if not path:
        return {"active": False}
    try:
        return {"active": True, "filename": path.name, "profile": profile_csv(path)}
    except Exception as exc:
        raise HTTPException(500, f"Active dataset is set but could not be read: {exc}")


@router.post("/upload")
async def upload_dataset(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a CSV file.")

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"File too large (max {MAX_UPLOAD_BYTES // (1024*1024)} MB).")
    if not contents.strip():
        raise HTTPException(400, "The uploaded file is empty.")

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_filename(file.filename)
    target = UPLOADS_DIR / f"{int(time.time())}_{safe_name}"
    target.write_bytes(contents)

    try:
        profile = profile_csv(target)  # schema + suggested dashboard/questions
        stats = analyze_dataset(target)  # real computed numbers
        summary_text = dataset_summary_text(target)
    except Exception as exc:
        logger.exception("Failed to analyze uploaded CSV %s", file.filename)
        target.unlink(missing_ok=True)
        raise HTTPException(400, f"Could not analyze CSV: {exc}")

    set_active_dataset(target)

    return {
        "filename": file.filename,
        "rows": stats["rows"],
        "profile": profile,
        "stats": stats,
        "summary_text": summary_text,
    }


@router.delete("/active")
def deactivate_dataset():
    """Stop grounding chat answers in the uploaded dataset and fall back
    to the built-in demo data."""
    clear_active_dataset()
    return {"active": False}
