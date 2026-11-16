"""User database: settings, cases + vault, pending sends, traces, outbound log, saved searches,
error reports, coverage gaps, uploaded documents, reminders. Never uploaded. Sensitive columns are
Fernet-encrypted (see crypto.KeyStore)."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .crypto import KeyStore

DDL = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS marked_term (term_hash TEXT PRIMARY KEY, term_enc BLOB NOT NULL, kind TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS legal_case (case_id TEXT PRIMARY KEY, label TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vault_entry (
  case_id TEXT NOT NULL, placeholder TEXT NOT NULL, kind TEXT NOT NULL, original_enc BLOB NOT NULL, key_hash TEXT NOT NULL,
  PRIMARY KEY (case_id, placeholder)
);
CREATE INDEX IF NOT EXISTS idx_vault_key ON vault_entry(case_id, kind, key_hash);
CREATE TABLE IF NOT EXISTS vault_alias (case_id TEXT NOT NULL, kind TEXT NOT NULL, alias_hash TEXT NOT NULL, placeholder TEXT NOT NULL, PRIMARY KEY (case_id, kind, alias_hash));
CREATE TABLE IF NOT EXISTS pending_query (
  query_id TEXT PRIMARY KEY, case_id TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
  status TEXT NOT NULL, payload_enc BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS trace (
  trace_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, case_id TEXT, status TEXT, payload_enc BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS outbound_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, kind TEXT NOT NULL, provider TEXT, model TEXT, host TEXT,
  case_id TEXT, sha256 TEXT, bytes INTEGER, latency_ms INTEGER, status TEXT, error TEXT, payload TEXT
);
CREATE TABLE IF NOT EXISTS saved_search (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, name TEXT NOT NULL, payload_enc BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS error_report (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, status TEXT NOT NULL, payload_enc BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS coverage_gap (
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, reason TEXT NOT NULL, domain TEXT, question_type TEXT, as_of TEXT, pack_version TEXT, question TEXT
);
CREATE TABLE IF NOT EXISTS document (
  doc_id TEXT PRIMARY KEY, case_id TEXT NOT NULL, created_at TEXT NOT NULL, filename TEXT, status TEXT NOT NULL,
  confidence REAL, payload_enc BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS reminder (
  id TEXT PRIMARY KEY, created_at TEXT NOT NULL, due_date TEXT NOT NULL, title TEXT NOT NULL, payload TEXT, done INTEGER NOT NULL DEFAULT 0
);
"""

DEFAULT_SETTINGS: dict[str, Any] = {
    "mode": None,                  # None -> Settings.default_mode
    "auto_approve_send": False,    # send preview required until the user switches this on
    "keep_places": True,           # keep city/court names (territorial jurisdiction)
    "strict_mode": False,          # send only structured facts, no free text
    "store_question_text": True,    # traces keep the PSEUDONYMISED question (never the raw one); False drops it
    "explain_language": None,      # None -> question language
    "citizen_mode": False,
    "weak_device": False,
    "benchmark": None,             # result of the first-launch benchmark
    "llm_providers": {},           # id -> {"kind": openai|anthropic|openai_compat, "label", "model", "base_url"}; the KEYS live in the keychain, never here
    "llm_active": None,            # id of the provider used to write answers (overrides the LEGALRAG_LLM_* environment values)
    "llm_checker": None, "llm_offline": None,           # id of a (different) provider that double-checks claims; None = the local lexical checker
    "provider_consent": {},        # provider name -> {"region":..., "dpa_signed": bool, "zero_retention": bool}
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class UserDB:
    def __init__(self, path: Path, keys: KeyStore):
        self.path = path
        self.keys = keys
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._c = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._c.row_factory = sqlite3.Row
        self._c.execute("PRAGMA journal_mode=WAL")
        self._c.executescript(DDL)

    # ---- low level ---------------------------------------------------------------------
    def execute(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._c.execute(sql, params)

    def query(self, sql: str, params: tuple | list = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._c.execute(sql, params).fetchall()

    def one(self, sql: str, params: tuple | list = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._c.execute(sql, params).fetchone()

    # ---- settings ----------------------------------------------------------------------
    def get_settings(self) -> dict[str, Any]:
        out = dict(DEFAULT_SETTINGS)
        for r in self.query("SELECT key,value FROM settings"):
            out[r["key"]] = json.loads(r["value"])
        return out

    def set_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        for k, v in updates.items():
            if k not in DEFAULT_SETTINGS:
                raise KeyError(k)
            self.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, json.dumps(v)))
        return self.get_settings()

    # ---- cases + vault ---------------------------------------------------------------------
    def create_case(self, label: str | None = None, case_id: str | None = None) -> str:
        cid = case_id or uuid.uuid4().hex[:12]
        self.execute("INSERT OR IGNORE INTO legal_case(case_id,label,created_at) VALUES(?,?,?)", (cid, label, now()))
        return cid

    def list_cases(self) -> list[dict]:
        rows = self.query(
            "SELECT c.case_id, c.label, c.created_at, (SELECT COUNT(*) FROM vault_entry v WHERE v.case_id=c.case_id) AS entities FROM legal_case c ORDER BY created_at DESC"
        )
        return [dict(r) for r in rows]

    def case_exists(self, case_id: str) -> bool:
        return self.one("SELECT 1 FROM legal_case WHERE case_id=?", (case_id,)) is not None

    def delete_case(self, case_id: str) -> None:
        """Wipes the vault mapping for a case and everything tied to it."""
        for t in ("vault_entry", "vault_alias", "pending_query", "document"):
            self.execute(f"DELETE FROM {t} WHERE case_id=?", (case_id,))
        self.execute("DELETE FROM trace WHERE case_id=?", (case_id,))
        self.execute("DELETE FROM outbound_log WHERE case_id=?", (case_id,))
        self.execute("DELETE FROM legal_case WHERE case_id=?", (case_id,))

    def vault_find(self, case_id: str, kind: str, key_hash: str) -> str | None:
        r = self.one("SELECT placeholder FROM vault_entry WHERE case_id=? AND kind=? AND key_hash=?", (case_id, kind, key_hash))
        if r:
            return r["placeholder"]
        a = self.one("SELECT placeholder FROM vault_alias WHERE case_id=? AND kind=? AND alias_hash=?", (case_id, kind, key_hash))
        return a["placeholder"] if a else None

    def vault_add(self, case_id: str, kind: str, original: str, key_hash: str, alias_hashes: list[str] | None = None) -> str:
        n = self.one("SELECT COUNT(*) AS n FROM vault_entry WHERE case_id=? AND kind=?", (case_id, kind))["n"]
        ph = f"[{kind}_{n + 1}]"
        self.execute(
            "INSERT INTO vault_entry(case_id,placeholder,kind,original_enc,key_hash) VALUES(?,?,?,?,?)",
            (case_id, ph, kind, self.keys.encrypt(original), key_hash),
        )
        for ah in alias_hashes or []:
            self.execute("INSERT OR IGNORE INTO vault_alias(case_id,kind,alias_hash,placeholder) VALUES(?,?,?,?)", (case_id, kind, ah, ph))
        return ph

    def vault_all(self, case_id: str) -> dict[str, tuple[str, str]]:
        """placeholder -> (kind, original). Decrypts; callers must keep it local."""
        rows = self.query("SELECT placeholder,kind,original_enc FROM vault_entry WHERE case_id=?", (case_id,))
        return {r["placeholder"]: (r["kind"], self.keys.decrypt(r["original_enc"])) for r in rows}

    # ---- marked terms (user-flagged missed names) ----------------------------------------------
    def add_marked_term(self, term: str, kind: str = "PERSON") -> None:
        h = self.keys.blind_index(term.strip().lower())
        self.execute(
            "INSERT OR IGNORE INTO marked_term(term_hash,term_enc,kind,created_at) VALUES(?,?,?,?)", (h, self.keys.encrypt(term.strip()), kind, now())
        )

    def marked_terms(self) -> list[tuple[str, str]]:
        return [(self.keys.decrypt(r["term_enc"]), r["kind"]) for r in self.query("SELECT term_enc,kind FROM marked_term")]

    def remove_marked_terms(self) -> None:
        self.execute("DELETE FROM marked_term")

    # ---- generic encrypted JSON rows ---------------------------------------------------------------
    def put_json(self, table: str, id_col: str, id_: str, enc_col: str, payload: Any, **cols: Any) -> None:
        fields = {id_col: id_, enc_col: self.keys.encrypt_json(payload), **cols}
        names = ",".join(fields)
        ph = ",".join("?" for _ in fields)
        upd = ",".join(f"{k}=excluded.{k}" for k in fields if k != id_col)
        self.execute(f"INSERT INTO {table}({names}) VALUES({ph}) ON CONFLICT({id_col}) DO UPDATE SET {upd}", list(fields.values()))

    def get_json(self, table: str, id_col: str, id_: str, enc_col: str) -> tuple[Any, sqlite3.Row] | None:
        r = self.one(f"SELECT * FROM {table} WHERE {id_col}=?", (id_,))
        if not r:
            return None
        return self.keys.decrypt_json(r[enc_col]), r

    # ---- pending queries -----------------------------------------------------------------------------
    def put_pending(self, query_id: str, case_id: str, payload: dict, status: str = "awaiting_approval", ttl_min: int = 30) -> None:
        exp = (datetime.now(timezone.utc) + timedelta(minutes=ttl_min)).isoformat(timespec="seconds")
        self.put_json("pending_query", "query_id", query_id, "payload_enc", payload, case_id=case_id, created_at=now(), expires_at=exp, status=status)

    def get_pending(self, query_id: str) -> tuple[dict, sqlite3.Row] | None:
        got = self.get_json("pending_query", "query_id", query_id, "payload_enc")
        if not got:
            return None
        payload, row = got
        if row["expires_at"] < now():
            self.execute("DELETE FROM pending_query WHERE query_id=?", (query_id,))
            return None
        return payload, row

    def purge_expired(self) -> None:
        self.execute("DELETE FROM pending_query WHERE expires_at < ?", (now(),))

    # ---- traces -----------------------------------------------------------------------------------------
    def put_trace(self, trace: dict, case_id: str | None) -> str:
        tid = trace.setdefault("trace_id", uuid.uuid4().hex)
        self.put_json("trace", "trace_id", tid, "payload_enc", trace, created_at=now(), case_id=case_id, status=trace.get("status"))
        return tid

    def get_trace(self, trace_id: str) -> dict | None:
        got = self.get_json("trace", "trace_id", trace_id, "payload_enc")
        return got[0] if got else None

    def list_traces(self, limit: int = 50) -> list[dict]:
        rows = self.query("SELECT trace_id,created_at,case_id,status FROM trace ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def clear_traces(self) -> int:
        n = self.execute("DELETE FROM trace").rowcount
        return n

    def purge_old_traces(self, days: int) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        self.execute("DELETE FROM trace WHERE created_at < ?", (cutoff,))

    # ---- outbound log -------------------------------------------------------------------------------------
    def log_outbound(self, **f: Any) -> int:
        cols = ["at", "kind", "provider", "model", "host", "case_id", "sha256", "bytes", "latency_ms", "status", "error", "payload"]
        f.setdefault("at", now())
        cur = self.execute(f"INSERT INTO outbound_log({','.join(cols)}) VALUES({','.join('?' for _ in cols)})", [f.get(c) for c in cols])
        return cur.lastrowid

    def update_outbound(self, id_: int, **f: Any) -> None:
        sets = ",".join(f"{k}=?" for k in f)
        self.execute(f"UPDATE outbound_log SET {sets} WHERE id=?", [*f.values(), id_])

    def list_outbound(self, limit: int = 100) -> list[dict]:
        return [dict(r) for r in self.query("SELECT * FROM outbound_log ORDER BY id DESC LIMIT ?", (limit,))]

    def clear_outbound(self) -> int:
        return self.execute("DELETE FROM outbound_log").rowcount

    # ---- coverage gaps ----------------------------------------------------------------------------------------
    def log_gap(self, reason: str, domain: str | None, question_type: str | None, as_of: str | None, pack_version: str | None, question: str | None) -> None:
        self.execute(
            "INSERT INTO coverage_gap(at,reason,domain,question_type,as_of,pack_version,question) VALUES(?,?,?,?,?,?,?)",
            (now(), reason, domain, question_type, as_of, pack_version, question),
        )

    def gap_summary(self) -> dict:
        by_reason = [dict(r) for r in self.query("SELECT reason, COUNT(*) AS n FROM coverage_gap GROUP BY reason ORDER BY n DESC")]
        by_domain = [dict(r) for r in self.query("SELECT COALESCE(domain,'unknown') AS domain, COUNT(*) AS n FROM coverage_gap GROUP BY domain ORDER BY n DESC")]
        recent = [dict(r) for r in self.query("SELECT * FROM coverage_gap ORDER BY id DESC LIMIT 50")]
        return {"by_reason": by_reason, "by_domain": by_domain, "recent": recent}

    def clear_gaps(self) -> int:
        return self.execute("DELETE FROM coverage_gap").rowcount

    def wipe_all(self) -> None:
        """One-click delete of history: traces, outbound log, gaps, saved searches, documents, pending sends."""
        for t in ("trace", "outbound_log", "coverage_gap", "saved_search", "document", "pending_query", "error_report"):
            self.execute(f"DELETE FROM {t}")

    def close(self) -> None:
        with self._lock:
            self._c.close()
