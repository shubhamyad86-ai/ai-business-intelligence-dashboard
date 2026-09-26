"""Small file-mtime-aware cache used by analytics functions."""
from __future__ import annotations
from pathlib import Path
from threading import RLock

_lock = RLock()
_cache: dict[str, tuple[int, int, object]] = {}

def cached_file_result(path: Path, builder):
    path = Path(path)
    stat = path.stat()
    key = str(path.resolve())
    signature = (stat.st_mtime_ns, stat.st_size)
    with _lock:
        item = _cache.get(key)
        if item and item[:2] == signature:
            return item[2]
    value = builder()
    with _lock:
        _cache[key] = (signature[0], signature[1], value)
    return value

def clear_cache() -> None:
    with _lock:
        _cache.clear()
