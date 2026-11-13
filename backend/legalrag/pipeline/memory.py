"""Long chat memory.  The server keeps each chat (LangChain message objects + `trim_messages`), so a follow-up is understood against the
WHOLE chat, not only the last few messages the browser sends:

    recent messages (as many as fit the budget)   +   a rolling summary of everything older

The summary is written by the same gateway as every other model call (so the privacy scan still runs on it); without a model it is a simple
extract.  Memory is never a legal source: answers still quote only passages found for the current question.
Chats live in server memory (lost on restart; the browser then re-seeds the chat from the messages it still has)."""
from __future__ import annotations

import re
import threading
import time
from typing import Any, Callable

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, trim_messages

RECENT_BUDGET_CHARS = 9000   # recent turns sent to the understanding step (about 3000 tokens)
FOLD_AT_CHARS = 14000        # when the stored chat is longer than this, the oldest part is folded into the summary
KEEP_TURNS = 10              # messages never folded
MAX_SESSIONS = 200
TTL_SECONDS = 6 * 3600
SUMMARY_MAX = 1800
SUMMARY_MARK = "[Earlier in this chat] "


def _chars(msgs: list[BaseMessage]) -> int:
    return sum(len(str(m.content)) for m in msgs)


class _Session:
    def __init__(self) -> None:
        self.messages: list[BaseMessage] = []
        self.summary = ""
        self.touched = time.time()


class ChatMemory:
    def __init__(self) -> None:
        self._s: dict[str, _Session] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------------------------------------------------ housekeeping
    def _gc(self) -> None:
        now = time.time()
        for k in [k for k, v in self._s.items() if now - v.touched > TTL_SECONDS]:
            del self._s[k]
        while len(self._s) > MAX_SESSIONS:
            del self._s[min(self._s, key=lambda k: self._s[k].touched)]

    def forget(self, session_id: str) -> None:
        with self._lock:
            self._s.pop(session_id, None)

    # ------------------------------------------------------------------------------------------------------------ read
    def context(self, session_id: str, browser_history: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        """Turns to use for this question: [summary of older turns] + recent turns, oldest first.  `browser_history` seeds an unknown chat."""
        with self._lock:
            self._gc()
            s = self._s.get(session_id)
            if s is None:
                s = self._s[session_id] = _Session()
                for h in browser_history or []:
                    self._append(s, h.get("role"), h.get("text") or "", h.get("cited") or [])
            s.touched = time.time()
            msgs = list(s.messages)
            summary = s.summary
        recent = trim_messages(msgs, max_tokens=RECENT_BUDGET_CHARS, token_counter=_chars, strategy="last", start_on="human", allow_partial=False) if msgs else []
        out = [{"role": "user" if isinstance(m, HumanMessage) else "assistant", "text": str(m.content), "cited": list(m.additional_kwargs.get("cited", []))} for m in recent]
        if summary:
            out.insert(0, {"role": "assistant", "text": SUMMARY_MARK + summary, "cited": []})
        return out

    # ------------------------------------------------------------------------------------------------------------ write
    @staticmethod
    def _append(s: _Session, role: str | None, text: str, cited: list[str]) -> None:
        text = re.sub(r"\s+", " ", text or "").strip()
        if not text:
            return
        cls = HumanMessage if role == "user" else AIMessage
        s.messages.append(cls(content=text[:3000], additional_kwargs={"cited": list(cited)[:50]}))

    def add_turn(self, session_id: str, question: str, answer: str, cited: list[str], summarizer: Callable[[str, list[dict[str, str]]], str | None] | None = None) -> None:
        """Record a finished exchange; fold the oldest part into the summary when the chat has grown long."""
        with self._lock:
            s = self._s.setdefault(session_id, _Session())
            self._append(s, "user", question, [])
            self._append(s, "assistant", answer, cited)
            s.touched = time.time()
            msgs = s.messages
            if _chars(msgs) <= FOLD_AT_CHARS or len(msgs) <= KEEP_TURNS:
                return
            old, keep = msgs[:-KEEP_TURNS], msgs[-KEEP_TURNS:]
            while keep and not isinstance(keep[0], HumanMessage):  # keep starts on a question
                old.append(keep.pop(0))
            prev = s.summary
        turns = [{"role": "user" if isinstance(m, HumanMessage) else "assistant", "text": str(m.content)} for m in old]
        new = None
        if summarizer is not None:
            try:
                new = summarizer(prev, turns)
            except Exception:  # noqa: BLE001 - the extract below is the floor
                new = None
        new = (new or extract_summary(prev, turns))[:SUMMARY_MAX]
        with self._lock:
            s = self._s.get(session_id)
            if s is None:
                return
            s.summary = new
            s.messages = list(keep)


def extract_summary(prev: str, turns: list[dict[str, str]]) -> str:
    """No model: the earlier questions, shortened."""
    parts = ([prev] if prev else []) + [t["text"][:120] for t in turns if t["role"] == "user"]
    while len(" | ".join(parts)) > SUMMARY_MAX and len(parts) > 1:
        parts.pop(0)  # the oldest questions go first, whole
    return " | ".join(parts)[-SUMMARY_MAX:]


_MEMORY: ChatMemory | None = None


def get_memory() -> ChatMemory:
    global _MEMORY
    if _MEMORY is None:
        _MEMORY = ChatMemory()
    return _MEMORY
