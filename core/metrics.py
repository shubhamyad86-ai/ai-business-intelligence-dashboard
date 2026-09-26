from __future__ import annotations
from threading import Lock
from time import perf_counter

_lock=Lock()
_state={"requests":0,"errors":0,"chat_requests":0,"chat_total_ms":0.0}

def observe_request(ms: float, error=False):
    with _lock:
        _state["requests"] += 1
        _state["errors"] += int(error)

def observe_chat(ms: float):
    with _lock:
        _state["chat_requests"] += 1
        _state["chat_total_ms"] += ms

def snapshot():
    with _lock:
        s=dict(_state)
    s["chat_avg_ms"] = round(s["chat_total_ms"]/s["chat_requests"],2) if s["chat_requests"] else 0
    return s
