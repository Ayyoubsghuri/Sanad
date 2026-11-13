"""Live steps of one question ("what the agent is doing"), polled by the app while the answer is being built and returned with it."""
from __future__ import annotations

import threading
import time
from contextvars import ContextVar
from typing import Any

_LOCK = threading.Lock()
_KEEP = 30  # queries remembered


class Progress:
    def __init__(self, store: dict[str, dict[str, Any]], qid: str):
        self.qid = qid
        with _LOCK:
            store[qid] = {"steps": [], "done": False}
            while len(store) > _KEEP:
                store.pop(next(iter(store)))
        self._rec = store[qid]
        self._t: dict[str, float] = {}

    def start(self, title: str, kind: str = "search", detail: str = "") -> str:
        with _LOCK:
            sid = f"s{len(self._rec['steps']) + 1}"
            self._rec["steps"].append({"id": sid, "kind": kind, "title": title, "detail": detail, "status": "running", "duration_ms": None})
            self._t[sid] = time.monotonic()
        return sid

    def done(self, sid: str, detail: str | None = None) -> None:
        with _LOCK:
            for s in self._rec["steps"]:
                if s["id"] == sid:
                    s["status"] = "done"
                    s["duration_ms"] = int((time.monotonic() - self._t.get(sid, time.monotonic())) * 1000)
                    if detail is not None:
                        s["detail"] = detail

    def finish(self) -> list[dict[str, Any]]:
        with _LOCK:
            for s in self._rec["steps"]:
                if s["status"] == "running":
                    s["status"] = "done"
                    s["duration_ms"] = int((time.monotonic() - self._t.get(s["id"], time.monotonic())) * 1000)
            self._rec["done"] = True
            return [dict(s) for s in self._rec["steps"]]


class _Noop:
    def start(self, *a: Any, **k: Any) -> str:
        return ""

    def done(self, *a: Any, **k: Any) -> None:
        return None

    def finish(self) -> list[dict[str, Any]]:
        return []


_CUR: ContextVar[Progress | None] = ContextVar("legalrag_progress", default=None)


def begin(store: dict[str, dict[str, Any]], qid: str) -> Progress:
    p = Progress(store, qid)
    _CUR.set(p)
    return p


def current() -> Progress | _Noop:
    return _CUR.get() or _Noop()


def snapshot(store: dict[str, dict[str, Any]], qid: str) -> dict[str, Any] | None:
    with _LOCK:
        r = store.get(qid)
        return None if r is None else {"steps": [dict(s) for s in r["steps"]], "done": r["done"]}
