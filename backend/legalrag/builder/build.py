"""Law pack builder (runs on YOUR machine, never on the user's device).

Input: a `sources` dict (see loader.py / fixtures.py for the shape). Output: a SQLite pack + signature file.
Pipeline: validate -> decide trust levels -> insert -> chunk -> FTS -> embed -> coverage report -> sign."""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from ..retrieval.embedders import Embedder
from ..store.schema_sql import LAWPACK_DDL
from ..store.signing import sign_pack
from ..text.arabic import keyword_text
from ..text.citations import parse_citations, prep_alias, provision_id_for
from . import checks
from .chunking import approx_tokens, context_prefix, make_chunks

BUILDER_VERSION = "1.0"
DATA = Path(__file__).resolve().parent.parent / "data"

FIXED_CIVIL_HOLIDAYS = [  # fixed-date civil holidays; religious (moon-dependent) dates must come from the sources
    ("01-01", "New Year's Day"), ("01-11", "Independence Manifesto Day"), ("01-14", "Amazigh New Year"), ("05-01", "Labour Day"),
    ("07-30", "Throne Day"), ("08-14", "Oued Ed-Dahab Day"), ("08-20", "Revolution of the King and the People"),
    ("08-21", "Youth Day"), ("11-06", "Green March Day"), ("11-18", "Independence Day"),
]


@dataclass
class BuildResult:
    path: Path
    sig_path: Path | None
    report: checks.Report
    stats: dict[str, Any]


def _registry() -> tuple[list[dict], dict]:
    return json.loads((DATA / "registry.json").read_text("utf-8")), json.loads((DATA / "registry_extras.json").read_text("utf-8"))


def build_pack(
    src: dict,
    out_path: Path,
    embedders: list[Embedder],
    pack_version: str,
    private_key_hex: str | None = None,
    allow_errors: bool = False,
    include_registry: bool = True,
    holiday_years: range = range(2024, 2031),
    built_at: str | None = None,
    pipeline=None,  # PipelineChunks: use the pipeline's chunks + vectors as they are (nothing is cut or embedded again)
) -> BuildResult:
    built_at = built_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    src = json.loads(json.dumps(src))  # work on a copy
    rep = checks.Report()
    checks.check_sources(src, rep)
    if not rep.ok and not allow_errors:
        return BuildResult(out_path, None, rep, {"built": False})

    if pipeline is not None:
        embedders = [pipeline.embedder]
    reg_inst, reg_extra = _registry() if include_registry else ([], {"rates": [], "pending_bills": []})
    instruments = {i["instrument_id"]: i for i in reg_inst}
    for i in src.get("instruments", []):
        instruments[i["instrument_id"]] = {**instruments.get(i["instrument_id"], {}), **i}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".building")
    for p in (tmp, out_path):
        if p.exists():
            p.unlink()
    db = sqlite3.connect(tmp)
    db.executescript(LAWPACK_DDL)
    cur = db.cursor()

    # ---- sources -------------------------------------------------------------------------------------------
    source_ids: dict[str, int] = {}
    for s in src.get("sources", []):
        cur.execute(
            "INSERT INTO source_file(url,fetched_at,sha256,kind,edition,label) VALUES(?,?,?,?,?,?)",
            (s.get("url"), s.get("fetched_at", built_at), s.get("sha256") or "unrecorded", s.get("kind", "other"), s.get("edition", "official"), s.get("label")),
        )
        source_ids[s["key"]] = cur.lastrowid

    # ---- instruments + aliases ------------------------------------------------------------------------------------
    alias_rows: set[tuple[str, str]] = set()
    registry_edges: list[tuple[str, str, str, str]] = []
    for iid, i in instruments.items():
        cur.execute(
            "INSERT INTO instrument(instrument_id,kind,number,short_code,title_ar,title_fr,bo_number,bo_date,promulgation_date,effective_date,ratification_date,"
            "language_availability,implementation_status,implementation_checked_on,status_flag,status_note,consolidated_text_available,official_article_count,domain) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (iid, i["kind"], i.get("number"), i.get("short_code"), i.get("title_ar"), i.get("title_fr"), i.get("bo_number"), i.get("bo_date"),
             i.get("promulgation_date"), i.get("effective_date"), i.get("ratification_date"), json.dumps(i.get("language_availability", {})),
             i.get("implementation_status", "unknown"), i.get("implementation_checked_on"), i.get("status_flag"), i.get("status_note"),
             int(bool(i.get("consolidated_text_available"))), i.get("official_article_count"), i.get("domain")),
        )
        for a in i.get("aliases", []):
            alias_rows.add((a, iid))
        if i.get("short_code"):
            alias_rows.add((i["short_code"], iid))
        for etype, target in i.get("edges", []):
            registry_edges.append(("instrument", iid, "instrument", target, etype))
    cur.executemany("INSERT INTO instrument_alias(alias,instrument_id) VALUES(?,?)", sorted(alias_rows))

    # ---- provisions, versions, texts -----------------------------------------------------------------------------------------
    version_rows: list[tuple[int, dict, dict]] = []  # (pv_id, provision, version)
    status_count: dict[str, int] = {}
    for p in src.get("provisions", []):
        num = str(p["number"]).strip()
        n_int = int(num.split()[0]) if num.split()[0].isdigit() else None
        suffix = num.split()[1].lower() if len(num.split()) > 1 else ""
        pid = p.get("provision_id") or provision_id_for(p["instrument_id"], n_int or 0, suffix)
        p["_pid"] = pid
        cur.execute(
            "INSERT INTO provision(provision_id,instrument_id,path,number,number_int,suffix,ordinal,is_definition,is_transitional) VALUES(?,?,?,?,?,?,?,?,?)",
            (pid, p["instrument_id"], p.get("path"), num, n_int, suffix, p.get("ordinal", n_int or 0), int(bool(p.get("is_definition"))), int(bool(p.get("is_transitional")))),
        )
        for v in p["versions"]:
            status = v.get("_status") or checks.decide_status(v)[0]
            sid = source_ids[v["source"]]
            body_ctrl = v["texts"].get(v.get("controlling_lang", "ar"), {}).get("text", "")
            cs = __import__("hashlib").sha256(body_ctrl.encode("utf-8")).hexdigest()
            cur.execute(
                "INSERT INTO provision_version(provision_id,valid_from,valid_to,controlling_lang,amended_by,source_id,checksum,verification_status) VALUES(?,?,?,?,?,?,?,?)",
                (pid, v["valid_from"], v.get("valid_to"), v.get("controlling_lang", "ar"), v.get("amended_by"), sid, cs, status),
            )
            pv_id = cur.lastrowid
            if p.get("page"):
                cur.execute("INSERT OR IGNORE INTO provision_page(provision_id,source_id,page_start,page_end) VALUES(?,?,?,?)", (pid, sid, int(p["page"]), int(p.get("page_end") or p["page"])))
            status_count[status] = status_count.get(status, 0) + 1
            for lang, t in v["texts"].items():
                cur.execute("INSERT INTO provision_text(pv_id,lang,edition,text) VALUES(?,?,?,?)", (pv_id, lang, t.get("edition", "official"), t["text"]))
            version_rows.append((pv_id, p, v))

    # ---- transitional rules, edges, rates, deadline rules, holidays, decisions, bills, concordance ---------------------------------------
    for t in src.get("transitional_rules", []):
        cur.execute(
            "INSERT INTO transitional_rule(instrument_id,applies_when,cutoff_date,note,source_provision_id,governs_version_before,governs_version_after) VALUES(?,?,?,?,?,?,?)",
            (t["instrument_id"], t["applies_when"], t.get("cutoff_date"), t["note"], t.get("source_provision_id"), t.get("governs_before"), t.get("governs_after")),
        )
    edges: dict[tuple, tuple] = {}
    for fk, fid, tk, tid, ty in registry_edges:
        edges[(fk, fid, tk, tid, ty)] = ("manual", 1.0)
    for e in src.get("edges", []):
        edges[(e.get("from_kind", "provision"), e["from"], e.get("to_kind", "provision"), e["to"], e["type"])] = (e.get("source", "manual"), e.get("confidence", 1.0))
    known_pids = {p["_pid"] for p in src.get("provisions", [])}
    aliases_all = {a: i for a, i in alias_rows}
    for _pv, p, v in version_rows:  # regex citation extraction: refers_to edges
        if v.get("valid_to"):
            continue
        for lang, t in v["texts"].items():
            for ref in parse_citations(t["text"], aliases_all):
                target_inst = ref.instrument_id or p["instrument_id"]
                tp = provision_id_for(target_inst, ref.number, ref.suffix)
                if tp in known_pids and tp != p["_pid"]:
                    key = ("provision", p["_pid"], "provision", tp, "refers_to")
                    edges.setdefault(key, ("regex", 0.95 if ref.instrument_id else 0.8))
    for (fk, fid, tk, tid, ty), (so, cf) in edges.items():
        cur.execute("INSERT OR IGNORE INTO edge(from_kind,from_id,to_kind,to_id,type,source,confidence) VALUES(?,?,?,?,?,?,?)", (fk, fid, tk, tid, ty, so, cf))
    for r in [*reg_extra.get("rates", []), *src.get("rates", [])]:
        cur.execute(
            "INSERT INTO rate_table(key,value,unit,valid_from,valid_to,source_decree,extra_json,note) VALUES(?,?,?,?,?,?,?,?)",
            (r["key"], r.get("value"), r.get("unit"), r["valid_from"], r.get("valid_to"), r.get("source_decree"), json.dumps(r["extra"]) if r.get("extra") else None, r.get("note")),
        )
    for d in src.get("deadline_rules", []):
        cur.execute(
            "INSERT INTO deadline_rule(kind,case_type,court,regime,trigger,amount,unit,valid_from,valid_to,provision_id,note) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (d["kind"], d["case_type"], d.get("court"), d.get("regime", "default"), d["trigger"], d["amount"], d["unit"], d.get("valid_from"), d.get("valid_to"), d.get("provision_id"), d.get("note")),
        )
    hol = {(h["date"], h["name"]): h for h in src.get("holidays", [])}
    for y in holiday_years:
        for md, name in FIXED_CIVIL_HOLIDAYS:
            if name == "Amazigh New Year" and y < 2024:
                continue
            hol.setdefault((f"{y}-{md}", name), {"date": f"{y}-{md}", "name": name, "kind": "civil", "source": "fixed civil holiday list: verify against the official calendar"})
    for h in hol.values():
        cur.execute("INSERT OR IGNORE INTO holiday(date,name,kind,source) VALUES(?,?,?,?)", (h["date"], h["name"], h["kind"], h.get("source")))
    for d in src.get("decisions", []):
        cur.execute("INSERT INTO decision(decision_id,court,decision_date,number,chamber,full_text,source_id) VALUES(?,?,?,?,?,?,?)",
                    (d["decision_id"], d.get("court"), d.get("decision_date"), d.get("number"), d.get("chamber"), d["full_text"], source_ids.get(d.get("source"))))
        for pid in d.get("provisions", []):
            cur.execute("INSERT OR IGNORE INTO decision_provision(decision_id,provision_id) VALUES(?,?)", (d["decision_id"], pid))
    for b in [*reg_extra.get("pending_bills", []), *src.get("pending_bills", [])]:
        cur.execute("INSERT OR REPLACE INTO pending_bill(bill_no,title,stage,last_checked,instrument_id,note) VALUES(?,?,?,?,?,?)",
                    (b["bill_no"], b.get("title"), b.get("stage"), b.get("last_checked"), b.get("instrument_id"), b.get("note")))
    for c in src.get("concordance", []):
        cur.execute("INSERT OR IGNORE INTO concordance(old_provision_id,new_provision_id,note,source) VALUES(?,?,?,?)", (c["old"], c["new"], c.get("note"), c.get("source", "derived")))

    # ---- chunks (+ FTS) ----------------------------------------------------------------------------------------------------------------
    chunk_rows: list[tuple[int, str]] = []
    pipe_vecs: list[np.ndarray] = []
    pipe_report = None
    if pipeline is not None:
        links, pipe_report = pipeline.plan(instruments, [(pv, p) for pv, p, _v in version_rows])
        for pv_id, ridx, para in links:
            r = pipeline.records[ridx]
            cur.execute("INSERT INTO chunk(pv_id,lang,edition,paragraph_no,body,text,keyword_text,token_count) VALUES(?,?,?,?,?,?,?,?)",
                        (pv_id, "ar", "official", para, r["content"], r["embed_text"], keyword_text(r["embed_text"]), int(r.get("tokens_est") or approx_tokens(r["content"]))))
            chunk_rows.append((cur.lastrowid, r["embed_text"]))
            pipe_vecs.append(pipeline.vectors[ridx])
    for pv_id, p, v in ([] if pipeline is not None else version_rows):
        inst = instruments[p["instrument_id"]]
        for lang, t in v["texts"].items():
            title = (inst.get("title_ar") if lang == "ar" else inst.get("title_fr")) or inst.get("title_fr") or inst.get("title_ar") or p["instrument_id"]
            prefix = context_prefix(lang, title, p.get("path"), p["number"], v["valid_from"], v.get("valid_to"))
            for ch in make_chunks(t["text"], prefix):
                cur.execute(
                    "INSERT INTO chunk(pv_id,lang,edition,paragraph_no,body,text,keyword_text,token_count) VALUES(?,?,?,?,?,?,?,?)",
                    (pv_id, lang, t.get("edition", "official"), ch.paragraph_no, ch.body, ch.text, keyword_text(ch.text), approx_tokens(ch.text)),
                )
                chunk_rows.append((cur.lastrowid, ch.text))
    cur.execute("INSERT INTO chunk_fts(chunk_fts) VALUES('rebuild')")

    # ---- embeddings ------------------------------------------------------------------------------------------------------------------------
    for emb in embedders:
        cur.execute("INSERT INTO embedder(embedder_id,model,version,dim) VALUES(?,?,?,?)", (emb.embedder_id, getattr(emb, "model", emb.embedder_id), BUILDER_VERSION, emb.dim))
        for i in range(0, len(chunk_rows), 64):
            batch = chunk_rows[i:i + 64]
            vecs = pipe_vecs[i:i + 64] if pipeline is not None else emb.embed([t for _, t in batch])
            cur.executemany(
                "INSERT INTO chunk_embedding(chunk_id,embedder_id,vector) VALUES(?,?,?)",
                [(cid, emb.embedder_id, np.asarray(v, dtype=np.float32).tobytes()) for (cid, _), v in zip(batch, vecs)],
            )

    # ---- coverage / trust report + meta -----------------------------------------------------------------------------------------------------------
    total = sum(status_count.values()) or 1
    meta = {
        "pack_version": pack_version, "built_at": built_at, "builder_version": BUILDER_VERSION, "schema_version": "1",
        "trust_counts": json.dumps(status_count), "trust_share": json.dumps({k: round(v / total, 4) for k, v in status_count.items()}),
        "check_report": json.dumps({"errors": len(rep.errors), "warnings": len(rep.warnings), "diffs": len(rep.diffs)}),
        "embedders": json.dumps([e.embedder_id for e in embedders]),
        "last_bo_check": src.get("last_bo_check", ""),
    }
    if pipeline is not None:
        meta["chunk_source"] = "pipeline"
        meta["pipeline_import"] = json.dumps(pipe_report, ensure_ascii=False)
    cur.executemany("INSERT INTO pack_meta(key,value) VALUES(?,?)", list(meta.items()))
    db.commit()
    db.execute("VACUUM")
    db.close()
    os.replace(tmp, out_path)
    sig = sign_pack(out_path, private_key_hex, built_at, pack_version) if private_key_hex else None
    return BuildResult(out_path, sig, rep, {"built": True, "versions": len(version_rows), "chunks": len(chunk_rows), "trust": status_count, **({"pipeline": pipe_report} if pipe_report else {})})
