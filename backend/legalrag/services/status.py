"""Law status card, amendment trail / time-travel, version diff, pack change notes, transitional wizard."""
from __future__ import annotations

import difflib
import json
from datetime import date
from typing import Any

from ..store.lawpack import LawPack
from ..text.arabic import normalize
from ..text.dates import parse_iso


def computed_status(pack: LawPack, instrument_id: str, as_of: date) -> dict[str, Any]:
    """IN_FORCE / NOT_YET_IN_FORCE / REPEALED is COMPUTED from version date ranges, never typed."""
    inst = pack.instrument(instrument_id)
    if not inst:
        return {"state": "UNKNOWN", "basis": "instrument not in the pack"}
    rows = pack._q(
        "SELECT MIN(pv.valid_from) AS first_from, MAX(CASE WHEN pv.valid_to IS NULL THEN 1 ELSE 0 END) AS open_ended, MAX(pv.valid_to) AS last_to, COUNT(*) AS n "
        "FROM provision_version pv JOIN provision p ON p.provision_id=pv.provision_id WHERE p.instrument_id=?", (instrument_id,))[0]
    eff = parse_iso(inst.get("effective_date"))
    if rows["n"]:
        first = date.fromisoformat(rows["first_from"])
        if as_of < first:
            state, basis = "NOT_YET_IN_FORCE", f"first text version starts {first.isoformat()}"
        elif rows["open_ended"] or (rows["last_to"] and date.fromisoformat(rows["last_to"]) > as_of):
            state, basis = "IN_FORCE", "at least one text version is valid on the date"
        else:
            state, basis = "REPEALED", f"all text versions ended by {rows['last_to']}"
    elif eff:
        state, basis = ("NOT_YET_IN_FORCE" if as_of < eff else "IN_FORCE"), f"no article text in the pack; effective date {eff.isoformat()} from instrument metadata"
    else:
        state, basis = "UNKNOWN", "no article text and no effective date in the pack"
    return {"state": state, "basis": basis, "text_in_pack": bool(rows["n"])}


def status_card(pack: LawPack, instrument_id: str, as_of: date, today: date) -> dict[str, Any] | None:
    inst = pack.instrument(instrument_id)
    if not inst:
        return None
    st = computed_status(pack, instrument_id, as_of)
    edges_out = pack.edges_from("instrument", instrument_id)
    edges_in = pack.edges_to("instrument", instrument_id)
    impl = inst["implementation_status"]
    checked = inst.get("implementation_checked_on")
    impl_text = {"self_executing": "self-executing: no implementing text needed", "issued": "implementing texts issued",
                 "pending": "implementing texts pending", "unknown": f"none found as of {checked}" if checked else "not checked"}[impl]
    if impl == "unknown" and checked:
        impl_text = f"no implementing text found as of {checked} (absence cannot be proven)"
    return {
        "instrument_id": instrument_id, "kind": inst["kind"], "number": inst["number"], "title_ar": inst["title_ar"], "title_fr": inst["title_fr"],
        "bo": {"number": inst["bo_number"], "date": inst["bo_date"]}, "promulgation_date": inst["promulgation_date"], "effective_date": inst["effective_date"],
        "as_of": as_of.isoformat(), "state": st["state"], "state_basis": st["basis"], "text_in_pack": st.get("text_in_pack"),
        "contested": inst["status_flag"] == "ACTIVE_CONTESTED", "status_flag": inst["status_flag"], "status_note": inst["status_note"],
        "language_availability": inst["language_availability"],
        "consolidated_text_available": bool(inst["consolidated_text_available"]),
        "implementation": {"status": impl, "checked_on": checked, "text": impl_text},
        "transitional_rules": pack.transitional_rules(instrument_id),
        "relations": {"amends": [e["to_id"] for e in edges_out if e["type"] == "amends"], "replaces": [e["to_id"] for e in edges_out if e["type"] == "replaces"],
                      "repeals": [e["to_id"] for e in edges_out if e["type"] == "repeals"], "implements": [e["to_id"] for e in edges_out if e["type"] == "implements"],
                      "amended_by": [e["from_id"] for e in edges_in if e["type"] == "amends"], "replaced_by": [e["from_id"] for e in edges_in if e["type"] == "replaces"],
                      "implemented_by": [e["from_id"] for e in edges_in if e["type"] == "implements"]},
        "pending_bills": [b for b in pack.pending_bills() if b["instrument_id"] == instrument_id],
        "pack": {"version": pack.version, "built_at": pack.built_at},
        "warnings": (["Contested text: check for updates."] if inst["status_flag"] == "ACTIVE_CONTESTED" else []),
    }


def provision_history(pack: LawPack, provision_id: str) -> dict[str, Any] | None:
    p = pack.provision(provision_id)
    if not p:
        return None
    out = []
    for v in pack.versions(provision_id):
        out.append({
            "pv_id": v["pv_id"], "valid_from": v["valid_from"], "valid_to": v["valid_to"], "trust": v["verification_status"],
            "amended_by": ({"instrument_id": v["amended_by"], "number": v["amender_number"], "bo_number": v["amender_bo"]} if v["amended_by"] else None),
            "texts": pack.texts(v["pv_id"]),
        })
    return {"provision": p, "versions": out}


def _words(t: str) -> list[str]:
    return t.split()


def diff_texts(a: str, b: str) -> list[dict[str, str]]:
    """Word-level diff segments: [{op: equal|insert|delete, text}]."""
    wa, wb = _words(a), _words(b)
    sm = difflib.SequenceMatcher(a=[normalize(w) for w in wa], b=[normalize(w) for w in wb], autojunk=False)
    segs: list[dict[str, str]] = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            segs.append({"op": "equal", "text": " ".join(wa[i1:i2])})
        else:
            if i2 > i1:
                segs.append({"op": "delete", "text": " ".join(wa[i1:i2])})
            if j2 > j1:
                segs.append({"op": "insert", "text": " ".join(wb[j1:j2])})
    return segs


def compare_dates(pack: LawPack, provision_id: str, d1: date, d2: date, lang: str = "ar") -> dict[str, Any] | None:
    v1, v2 = pack.version_at(provision_id, d1), pack.version_at(provision_id, d2)
    if not v1 and not v2:
        return None
    t1 = (pack.texts(v1["pv_id"]).get(lang) or {}).get("text", "") if v1 else ""
    t2 = (pack.texts(v2["pv_id"]).get(lang) or {}).get("text", "") if v2 else ""
    return {
        "provision_id": provision_id, "lang": lang, "same_version": bool(v1 and v2 and v1["pv_id"] == v2["pv_id"]),
        "from": {"date": d1.isoformat(), "version": v1 and {"valid_from": v1["valid_from"], "valid_to": v1["valid_to"], "trust": v1["verification_status"]}, "text": t1},
        "to": {"date": d2.isoformat(), "version": v2 and {"valid_from": v2["valid_from"], "valid_to": v2["valid_to"], "trust": v2["verification_status"]}, "text": t2},
        "diff": diff_texts(t1, t2),
    }


def pack_changes(new: LawPack, old: LawPack | None) -> dict[str, Any]:
    """Law-change notes between two packs: new / changed / removed article versions (before-and-after)."""
    if old is None:
        return {"previous_pack": None, "changes": []}
    a, b = old.provision_checksums(), new.provision_checksums()
    changes: list[dict[str, Any]] = []
    for key, cs in b.items():
        if key not in a:
            changes.append({"provision_id": key[0], "valid_from": key[1], "change": "added"})
        elif a[key] != cs:
            changes.append({"provision_id": key[0], "valid_from": key[1], "change": "text_changed"})
    for key in a:
        if key not in b:
            changes.append({"provision_id": key[0], "valid_from": key[1], "change": "removed"})
    return {"previous_pack": old.version, "new_pack": new.version, "changes": sorted(changes, key=lambda c: (c["provision_id"], c["valid_from"]))}


def which_rules_apply(pack: LawPack, instrument_id: str, filing_date: date | None, judgment_date: date | None, facts_date: date | None) -> dict[str, Any]:
    """Shows the transitional rule text, the date comparisons as written, and both versions. It does NOT decide which applies."""
    rules = pack.transitional_rules(instrument_id)
    given = {"filed": filing_date, "judgment": judgment_date, "facts": facts_date}
    out = []
    for r in rules:
        kind, _, rel = r["applies_when"].partition("_")  # e.g. judgment_before -> ('judgment','before')
        d, cutoff = given.get(kind), parse_iso(r["cutoff_date"])
        cmp_text = None
        if d and cutoff:
            cmp_text = f"{kind} date {d.isoformat()} is {'before' if d < cutoff else 'on or after'} {cutoff.isoformat()}"
        elif cutoff:
            cmp_text = f"condition: {r['applies_when'].replace('_', ' ')} {cutoff.isoformat()} (date not provided)"
        src = pack.provision(r["source_provision_id"]) if r["source_provision_id"] else None
        out.append({**r, "date_comparison": cmp_text, "source_provision": src})
    versions = []
    for p in pack.provisions_of(instrument_id):
        vs = pack.versions(p["provision_id"])
        if len(vs) > 1:
            versions.append({"provision_id": p["provision_id"], "versions": [{"valid_from": v["valid_from"], "valid_to": v["valid_to"], "trust": v["verification_status"]} for v in vs]})
    inst = pack.instrument(instrument_id)
    old_ids = [e["to_id"] for e in pack.edges_from("instrument", instrument_id) if e["type"] in ("replaces", "amends", "repeals")]
    return {
        "instrument_id": instrument_id, "effective_date": inst and inst["effective_date"], "transitional_rules": out, "affected_instruments": old_ids,
        "articles_with_multiple_versions": versions,
        "concordance": pack.concordance(new_instrument=instrument_id),
        "notice": "This tool shows the rule text and both versions. It does not decide which applies: read the transitional text or consult a legal professional.",
    }
