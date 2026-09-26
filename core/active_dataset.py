"""
core/active_dataset.py
------------------------
Tracks which uploaded custom dataset (if any) is "active" — the one the
chat agent should ground answers in. Backed by a small JSON pointer file
so it survives server restarts without needing a database.

This is intentionally separate from the built-in demo data (sales.csv,
inventory.csv): uploading a dataset doesn't overwrite or touch those, it
just tells the agent "also consider this."
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
POINTER_FILE = DATA_DIR / "active_dataset.json"


def set_active_dataset(csv_path: Path) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    POINTER_FILE.write_text(json.dumps({"path": str(csv_path)}), encoding="utf-8")


def get_active_dataset_path() -> Optional[Path]:
    if not POINTER_FILE.exists():
        return None
    try:
        data = json.loads(POINTER_FILE.read_text(encoding="utf-8"))
        path = Path(data["path"])
        return path if path.exists() else None
    except Exception:
        return None


def clear_active_dataset() -> None:
    POINTER_FILE.unlink(missing_ok=True)
