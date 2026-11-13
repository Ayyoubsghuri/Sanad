"""Add new Bulletin Officiel texts to an EXISTING law pack (incremental update; the full build_pack stays the way to start).

Input: the `sources` dict that `from_bo.bo_to_sources` makes for the NEW issues only. The pack file is changed in place, so the caller works on a COPY
(see bo_update.runner): nothing is replaced until the copy is complete, signed and verified.

What is added: source files, instruments, provisions with one dated version each, texts, edges (also to instruments already in the pack), chunks
(same chunking as build_pack), the keyword index and the vectors of the pack's own embedder.  What is never touched: rates, holidays, decisions,
deadline rules, bills, concordance, and every row that was already in the pack."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np

from ..retrieval.embedders import Embedder
from ..store.signing import sign_pack
from ..text.arabic import keyword_text
from ..text.citations import provision_id_for
from . import checks
from .chunking import approx_tokens, context_prefix, make_chunks


class AppendError(Exception):
    pass


def append_sources(
    pack_path: Path,
    src: dict,
    embedder: Embedder,
    pack_version: str,
    private_key_hex: str | None = None,
    progress: Callable[[str, int, int], None] | None = None,
    built_at: str | None = None,
    pipeline=None,  # PipelineChunks for the NEW issues: stored with their own vectors, nothing is cut or embedded here
) -> dict:
    """-> {"instruments": n, "articles": n, "chunks": n, "skipped_existing": [...], "report": {...}}"""
    built_at = built_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    src = json.loads(json.dumps(src))
    db = sqlite3.connect(pack_path)
    db.row_factory = sqlite3.Row
    try:
        packs = {r["embedder_id"]: r for r in db.execute("SELECT embedder_id,dim FROM embedder")}
        if pipeline is not None:
            embedder = pipeline.embedder
            if embedder.embedder_id not in packs:
                raise AppendError(f"the pack's vectors are '{sorted(packs)}', the new chunks were embedded as '{embedder.embedder_id}' ({embedder.model}): use the same model and settings as for the first run")
            row = db.execute("SELECT model FROM embedder WHERE embedder_id=?", (embedder.embedder_id,)).fetchone()
            if row and row["model"] and row["model"] != embedder.model:
                raise AppendError(f"the pack was embedded with {row['model']}, the new chunks with {embedder.model}")
        if embedder.embedder_id not in packs:
            raise AppendError(f"the pack was built with embedder(s) {sorted(packs)}; this machine would use '{embedder.embedder_id}'. "
                              "New text must be embedded by the same model, otherwise search would silently ignore it.")
        if int(packs[embedder.embedder_id]["dim"]) != int(embedder.dim):
            raise AppendError(f"embedder dimension differs: pack {packs[embedder.embedder_id]['dim']} vs {embedder.dim}")

        existing_inst = {r["instrument_id"] for r in db.execute("SELECT instrument_id FROM instrument")}
        existing_prov = {r["provision_id"] for r in db.execute("SELECT provision_id FROM provision")}
        existing_sha = {r["sha256"] for r in db.execute("SELECT sha256 FROM source_file WHERE kind='bo_pdf'")}

        # an issue whose PDF is already in the pack is skipped as a whole (re-running an update must change nothing)
        skip_keys = {s["key"] for s in src.get("sources", []) if s.get("sha256") and s["sha256"] in existing_sha}
        keep_instr = [i for i in src.get("instruments", []) if f"BO_{i.get('bo_number')}" not in skip_keys]
        # same type+number already in the pack: a republication / corrigendum, kept NEXT TO the old one (never overwrites it)
        rename: dict[str, str] = {}
        taken = set(existing_inst)
        for i in keep_instr:
            iid = i["instrument_id"]
            if iid in existing_inst:
                new, n = f"{iid}_BO{i.get('bo_number') or 'v2'}", 2
                while new in taken:
                    new, n = f"{iid}_BO{i.get('bo_number') or 'v2'}_{n}", n + 1
                rename[iid] = new
                i["instrument_id"] = new
            taken.add(i["instrument_id"])
        keep_ids = {i["instrument_id"] for i in keep_instr}
        provs = []
        for p in src.get("provisions", []):
            old = p["instrument_id"]
            p["instrument_id"] = rename.get(old, old)
            if old in rename and p.get("provision_id", "").startswith(old + "_ART_"):
                p["provision_id"] = rename[old] + p["provision_id"][len(old):]
            if p["instrument_id"] in keep_ids:
                provs.append(p)
        by_old = rename
        ids_ok = keep_ids
        sub = {"sources": [s for s in src.get("sources", []) if s["key"] not in skip_keys], "instruments": keep_instr, "provisions": provs, "edges": []}
        rep = checks.Report()
        checks.check_sources(sub, rep)
        if not rep.ok:
            raise AppendError("checks failed on the new texts: " + "; ".join(f"{e['code']} {e['where']}" for e in rep.errors[:5]))

        cur = db.cursor()
        source_ids: dict[str, int] = {}
        for s in sub["sources"]:
            cur.execute("INSERT INTO source_file(url,fetched_at,sha256,kind,edition,label) VALUES(?,?,?,?,?,?)",
                        (s.get("url"), s.get("fetched_at", built_at), s.get("sha256") or "unrecorded", s.get("kind", "other"), s.get("edition", "official"), s.get("label")))
            source_ids[s["key"]] = cur.lastrowid
        for i in sub["instruments"]:
            cur.execute(
                "INSERT INTO instrument(instrument_id,kind,number,short_code,title_ar,title_fr,bo_number,bo_date,promulgation_date,effective_date,ratification_date,"
                "language_availability,implementation_status,implementation_checked_on,status_flag,status_note,consolidated_text_available,official_article_count,domain) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (i["instrument_id"], i["kind"], i.get("number"), i.get("short_code"), i.get("title_ar"), i.get("title_fr"), i.get("bo_number"), i.get("bo_date"),
                 i.get("promulgation_date"), i.get("effective_date"), i.get("ratification_date"), json.dumps(i.get("language_availability", {})),
                 i.get("implementation_status", "unknown"), i.get("implementation_checked_on"), i.get("status_flag"), i.get("status_note"),
                 int(bool(i.get("consolidated_text_available"))), i.get("official_article_count"), i.get("domain")))
        instruments = {i["instrument_id"]: i for i in sub["instruments"]}

        rows: list[tuple[int, dict, dict]] = []
        added_pids: set[str] = set()
        for p in sub["provisions"]:
            num = str(p["number"]).strip()
            n_int = int(num.split()[0]) if num.split()[0].isdigit() else None
            suffix = num.split()[1].lower() if len(num.split()) > 1 else ""
            pid = p.get("provision_id") or provision_id_for(p["instrument_id"], n_int or 0, suffix)
            if pid in existing_prov or pid in added_pids:
                continue
            added_pids.add(pid)
            p["_pid"] = pid
            cur.execute("INSERT INTO provision(provision_id,instrument_id,path,number,number_int,suffix,ordinal,is_definition,is_transitional) VALUES(?,?,?,?,?,?,?,?,?)",
                        (pid, p["instrument_id"], p.get("path"), num, n_int, suffix, p.get("ordinal", n_int or 0), int(bool(p.get("is_definition"))), int(bool(p.get("is_transitional")))))
            for v in p["versions"]:
                status = v.get("_status") or checks.decide_status(v)[0]
                body = v["texts"].get(v.get("controlling_lang", "ar"), {}).get("text", "")
                cs = __import__("hashlib").sha256(body.encode("utf-8")).hexdigest()
                cur.execute("INSERT INTO provision_version(provision_id,valid_from,valid_to,controlling_lang,amended_by,source_id,checksum,verification_status) VALUES(?,?,?,?,?,?,?,?)",
                            (pid, v["valid_from"], v.get("valid_to"), v.get("controlling_lang", "ar"), v.get("amended_by"), source_ids[v["source"]], cs, status))
                pv_id = cur.lastrowid
                if p.get("page"):
                    db.execute("CREATE TABLE IF NOT EXISTS provision_page (provision_id TEXT NOT NULL, source_id INTEGER NOT NULL, page_start INTEGER NOT NULL, page_end INTEGER NOT NULL, PRIMARY KEY (provision_id, source_id))")
                    cur.execute("INSERT OR IGNORE INTO provision_page(provision_id,source_id,page_start,page_end) VALUES(?,?,?,?)",
                                (pid, source_ids[v["source"]], int(p["page"]), int(p.get("page_end") or p["page"])))
                for lang, t in v["texts"].items():
                    cur.execute("INSERT INTO provision_text(pv_id,lang,edition,text) VALUES(?,?,?,?)", (pv_id, lang, t.get("edition", "official"), t["text"]))
                rows.append((pv_id, p, v))

        # edges: from the new texts to anything now in the pack (new or old instruments)
        all_inst = existing_inst | ids_ok
        n_edges = 0
        for e in src.get("edges", []):
            f, t = by_old.get(e["from"], e["from"]), by_old.get(e["to"], e["to"])
            if f in ids_ok and t in all_inst and f != t:
                cur.execute("INSERT OR IGNORE INTO edge(from_kind,from_id,to_kind,to_id,type,source,confidence) VALUES(?,?,?,?,?,?,?)",
                            (e.get("from_kind", "instrument"), f, e.get("to_kind", "instrument"), t, e["type"], e.get("source", "regex"), e.get("confidence", 0.9)))
                n_edges += 1

        chunk_rows: list[tuple[int, str]] = []
        pipe_vecs: list[np.ndarray] = []
        pipe_report = None
        if pipeline is not None:
            links, pipe_report = pipeline.plan(instruments, [(pv, p) for pv, p, _v in rows])
            for pv_id, ridx, para in links:
                r = pipeline.records[ridx]
                cur.execute("INSERT INTO chunk(pv_id,lang,edition,paragraph_no,body,text,keyword_text,token_count) VALUES(?,?,?,?,?,?,?,?)",
                            (pv_id, "ar", "official", para, r["content"], r["embed_text"], keyword_text(r["embed_text"]), int(r.get("tokens_est") or approx_tokens(r["content"]))))
                cid = cur.lastrowid
                cur.execute("INSERT INTO chunk_fts(rowid,keyword_text) VALUES(?,?)", (cid, keyword_text(r["embed_text"])))
                chunk_rows.append((cid, r["embed_text"]))
                pipe_vecs.append(pipeline.vectors[ridx])
        else:
            for pv_id, p, v in rows:
                inst = instruments[p["instrument_id"]]
                for lang, t in v["texts"].items():
                    title = (inst.get("title_ar") if lang == "ar" else inst.get("title_fr")) or inst.get("title_fr") or inst.get("title_ar") or p["instrument_id"]
                    prefix = context_prefix(lang, title, p.get("path"), p["number"], v["valid_from"], v.get("valid_to"))
                    for ch in make_chunks(t["text"], prefix):
                        cur.execute("INSERT INTO chunk(pv_id,lang,edition,paragraph_no,body,text,keyword_text,token_count) VALUES(?,?,?,?,?,?,?,?)",
                                    (pv_id, lang, t.get("edition", "official"), ch.paragraph_no, ch.body, ch.text, keyword_text(ch.text), approx_tokens(ch.text)))
                        cid = cur.lastrowid
                        cur.execute("INSERT INTO chunk_fts(rowid,keyword_text) VALUES(?,?)", (cid, keyword_text(ch.text)))
                        chunk_rows.append((cid, ch.text))

        total = len(chunk_rows)
        for i in range(0, total, 32):
            batch = chunk_rows[i:i + 32]
            vecs = pipe_vecs[i:i + 32] if pipeline is not None else embedder.embed([t for _, t in batch])
            cur.executemany("INSERT INTO chunk_embedding(chunk_id,embedder_id,vector) VALUES(?,?,?)",
                            [(cid, embedder.embedder_id, np.asarray(v, dtype=np.float32).tobytes()) for (cid, _), v in zip(batch, vecs)])
            if progress:
                progress("embed", min(i + 32, total), total)

        # trust statistics + meta
        counts = {r["verification_status"]: r["n"] for r in db.execute("SELECT verification_status, COUNT(*) AS n FROM provision_version GROUP BY 1")}
        tot = sum(counts.values()) or 1
        for k, v in {"pack_version": pack_version, "built_at": built_at, "trust_counts": json.dumps(counts),
                     "trust_share": json.dumps({k: round(n / tot, 4) for k, n in counts.items()}), "last_bo_check": built_at[:10]}.items():
            cur.execute("INSERT INTO pack_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
        db.commit()
        result = {"instruments": len(sub["instruments"]), "articles": len(rows), "chunks": total, "edges": n_edges,
                  "skipped_existing": sorted(skip_keys), "renamed": by_old, "report": rep.to_dict(), "pipeline": pipe_report}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    if private_key_hex:
        sign_pack(pack_path, private_key_hex, built_at, pack_version)
    return result
