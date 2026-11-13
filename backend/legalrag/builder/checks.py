"""Automated source checks that substitute for a lawyer reviewer (blueprint: "Accuracy without lawyer review").

Errors block the build; warnings go into the build report. Nothing here is a legal judgement: it is text hygiene,
numbering, count, overlap, checksum and Arabic/French agreement."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from ..text.arabic import normalize, numbers_in, presentation_form_count


@dataclass
class Report:
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    diffs: list[dict] = field(default_factory=list)  # second-source disagreements to resolve by reading the PDF
    stats: dict = field(default_factory=dict)

    def err(self, code: str, where: str, detail: str = "") -> None:
        self.errors.append({"code": code, "where": where, "detail": detail})

    def warn(self, code: str, where: str, detail: str = "") -> None:
        self.warnings.append({"code": code, "where": where, "detail": detail})

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings, "diffs": self.diffs, "stats": self.stats}


def _d(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def decide_status(version: dict) -> tuple[str, dict | None]:
    """verified = two OFFICIAL sources agree on the controlling-language text; single_source = one; derived = built by
    applying amending laws; disputed = sources disagree. An unofficial translation never counts as a second source."""
    if version.get("derived"):
        return "derived", None
    lang = version.get("controlling_lang", "ar")
    primary = (version["texts"].get(lang) or {}).get("text", "")
    second = (version.get("second_texts") or {}).get(lang)
    if second and (second.get("edition", "official") == "official"):
        if normalize(second["text"]) == normalize(primary):
            return "verified", None
        return "disputed", {"primary": primary, "second": second["text"]}
    return "single_source", None


def check_sources(src: dict, rep: Report, version_status: dict[tuple[str, str], str] | None = None) -> None:
    sources = src.get("sources", [])
    from ..store.signing import sha256_file
    from pathlib import Path

    for s in sources:
        p = s.get("path")
        if p and Path(p).exists():
            actual = sha256_file(Path(p))
            if s.get("sha256") and s["sha256"] != actual:
                rep.err("checksum_mismatch", s["key"], f"declared {s['sha256']} != file {actual}")
            s["sha256"] = actual
        elif not s.get("sha256"):
            rep.warn("source_without_hash", s["key"], "no raw file or hash recorded: provenance cannot be re-checked")

    by_instr: dict[str, list[dict]] = {}
    for p in src.get("provisions", []):
        by_instr.setdefault(p["instrument_id"], []).append(p)

    instruments = {i["instrument_id"]: i for i in src.get("instruments", [])}
    for iid, provs in by_instr.items():
        if iid not in instruments:
            rep.err("unknown_instrument", iid, "provision refers to an instrument that is not defined")
            continue
        # numbering gaps (plain integers; bis/ter excluded), count vs official count
        nums = sorted({int(re.match(r"\d+", p["number"]).group()) for p in provs if re.match(r"\d+", p["number"])})
        if nums:
            missing = [n for n in range(nums[0], nums[-1] + 1) if n not in set(nums)]
            if missing:
                rep.warn("numbering_gap", iid, f"missing article numbers: {missing[:20]}{'...' if len(missing) > 20 else ''}")
        official = instruments[iid].get("official_article_count")
        if official and len(provs) != official:
            rep.warn("article_count_mismatch", iid, f"{len(provs)} ingested vs {official} official")

        for p in provs:
            where = f"{iid} art. {p['number']}"
            vers = sorted(p.get("versions", []), key=lambda v: v["valid_from"])
            if not vers:
                rep.err("no_versions", where)
            for i, v in enumerate(vers):
                vf, vt = _d(v["valid_from"]), _d(v.get("valid_to"))
                if vt and vf >= vt:
                    rep.err("bad_range", where, f"valid_from {vf} >= valid_to {vt}")
                if i + 1 < len(vers):
                    nxt = _d(vers[i + 1]["valid_from"])
                    if vt is None or vt > nxt:
                        rep.err("overlapping_versions", where, f"{v['valid_from']} overlaps {vers[i + 1]['valid_from']}")
                    elif vt < nxt:
                        rep.warn("gap_between_versions", where, f"no text between {vt} and {nxt}")
                texts = v.get("texts", {})
                if not texts:
                    rep.err("no_text", where, v["valid_from"])
                for lang, t in texts.items():
                    body = (t.get("text") or "").strip()
                    if len(body) < 10:
                        if re.search(r"نسخ|تنسخ|ينسخ|ألغ|الغ|يلغ|تلغ|ملغ|محذوف|abrog|supprim|repeal|sans objet|r[ée]serv", body, re.I):
                            rep.warn("repealed_article", where, f"{lang}: {body!r}")  # a repealed article keeps its number with a one-word text
                        else:
                            rep.err("empty_or_truncated", where, f"{lang} text is empty or very short")
                    if lang == "ar" and presentation_form_count(body) > 0:
                        rep.err("broken_arabic_order", where, "Arabic presentation forms found: probably visual-order PDF extraction; re-extract or OCR")
                # Arabic / French alignment: a mismatch makes the article disputed until read against the source
                ar, fr = (texts.get("ar") or {}).get("text"), (texts.get("fr") or {}).get("text")
                if ar and fr:
                    if sorted(numbers_in(ar)) != sorted(numbers_in(fr)):
                        v["_align_mismatch"] = True
                        rep.diffs.append({"where": where, "valid_from": v["valid_from"], "kind": "ar_fr_numbers", "ar_numbers": numbers_in(ar), "fr_numbers": numbers_in(fr)})
                elif v.get("controlling_lang", "ar") == "ar" and not ar:
                    rep.err("controlling_text_missing", where, "controlling language 'ar' has no text")
                status, diff = decide_status(v)
                if diff:
                    rep.diffs.append({"where": where, "valid_from": v["valid_from"], "kind": "second_source", **diff})
                if v.get("_align_mismatch") and status in ("verified", "single_source"):
                    status = "disputed"
                v["_status"] = status
    for e in src.get("edges", []):
        pass
    rep.stats["articles"] = sum(len(v) for v in by_instr.values())
