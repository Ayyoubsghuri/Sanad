"""Contract / document checker and guides generated from the pack.

Contract checker: the masked text of an uploaded document (names are placeholders) is cut into clauses; each clause is searched in the
law pack; ONE model call classifies every clause against the articles found (consistent / conflicts / check / no_rule).  A finding is kept only
if its quote is really inside the article it names; the articles the document cites itself are shown with their text on the date.  Without a
model the clauses come back with the articles found, unclassified.  Nothing here is advice: findings point at articles to read.

Guides: a list of articles for a situation, grouped by topic, built from the pack at request time (never typed), cached per pack version."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from ..llm.providers import GenRequest
from ..retrieval.engine import RetrievalRequest
from ..state import AppContext
from ..text.arabic import normalize
from ..text.citations import parse_citations
from ..verify import renderer
from . import documents as docs

DISCLAIMER = {"ar": "فحص آلي يشير إلى مواد للقراءة وليس رأيا قانونيا. اعرض العقد على مختص قبل التوقيع.",
              "fr": "Contrôle automatique qui désigne des articles à lire ; ce n'est pas un avis juridique. Faites relire le contrat par un professionnel avant de signer.",
              "en": "An automatic check that points at articles to read; it is not legal advice. Have a professional read the contract before signing."}

_CLAUSE_SPLIT = re.compile(r"\n\s*\n|\n(?=\s*(?:المادة|الفصل|البند|Article|ARTICLE|Art\.|\d{1,2}[\.\)\-–]\s))", re.U)
_MIN_CLAUSE, _MAX_CLAUSE, _MAX_CLAUSES = 40, 900, 40


def split_clauses(text: str) -> list[dict[str, Any]]:
    """[{n, title, text}]: a paragraph or numbered clause each; very short pieces join the previous one, very long ones are cut at a sentence."""
    parts = [p.strip() for p in _CLAUSE_SPLIT.split(text or "") if p and p.strip()]
    merged: list[str] = []
    for p in parts:
        if merged and len(p) < _MIN_CLAUSE:
            merged[-1] += "\n" + p
        else:
            merged.append(p)
    out: list[dict[str, Any]] = []
    for p in merged:
        while len(p) > _MAX_CLAUSE:
            cut = max(p.rfind(".", 0, _MAX_CLAUSE), p.rfind("؛", 0, _MAX_CLAUSE), p.rfind("\n", 0, _MAX_CLAUSE))
            cut = cut if cut > _MAX_CLAUSE // 2 else _MAX_CLAUSE
            out.append({"text": p[:cut + 1].strip()})
            p = p[cut + 1:].strip()
        if p:
            out.append({"text": p})
    out = [c for c in out if len(c["text"]) >= _MIN_CLAUSE][:_MAX_CLAUSES]
    for i, c in enumerate(out, 1):
        c["n"] = i
        c["title"] = c["text"].split("\n", 1)[0][:80]
    return out


SYSTEM = """You check a contract / document against Moroccan law articles. You are given numbered CLAUSES of the document and numbered PASSAGES (law articles, each with an id).
For each clause that touches a rule in the passages, give one finding:
- verdict: "consistent" (the clause follows the article), "conflicts" (the clause says the opposite of, or goes below, a rule the article makes mandatory), "check" (a rule applies that the reader must look at, or the clause is unclear), or "no_rule" (no passage deals with it - then omit the finding).
- passage: the id of the article your finding rests on. quote: a SHORT exact quote copied from THAT passage. why: one sentence in the reader's language.
Rules: use ONLY the passages; never invent an article or a number; a rule that parties may change by agreement is not a conflict; when unsure say "check". Do not advise, draft or predict a court result. Skip clauses that are only names, dates or signatures."""

SCHEMA = {"type": "object", "properties": {"findings": {"type": "array", "items": {"type": "object", "properties": {
    "clause": {"type": "integer"}, "verdict": {"type": "string", "enum": ["consistent", "conflicts", "check"]}, "passage": {"type": "string"},
    "quote": {"type": "string"}, "why": {"type": "string"}}, "required": ["clause", "verdict", "passage", "quote", "why"]}}}, "required": ["findings"]}


def _quote_in(quote: str, text: str) -> bool:
    q = re.sub(r"\s+", "", normalize(quote or ""))
    return len(q) >= 8 and q in re.sub(r"\s+", "", normalize(text or ""))


def check_document(ctx: AppContext, doc_id: str | None, text: str | None, as_of: date | None, lang: str, case_id: str | None = None) -> dict[str, Any]:
    pack = ctx.pack
    assert pack is not None
    when = as_of or ctx.today_fn()
    if doc_id:
        pseudo, status = docs.get_pseudonymised(ctx, doc_id)  # KeyError -> 404 in the router
        if status not in ("ready", "reviewed"):
            raise PermissionError(f"document {doc_id} needs review before the checker can use it")
        case_id = case_id or (ctx.db.one("SELECT case_id FROM document WHERE doc_id=?", (doc_id,)) or {"case_id": None})["case_id"]
        raw = None
    else:
        pseudo, raw = text or "", text
        if not pseudo.strip():
            raise ValueError("give doc_id (an uploaded document) or text")
        case_id = case_id or ctx.db.create_case()
        pseudo = ctx.pseudo.pseudonymise(pseudo, case_id, keep_places=ctx.user_settings()["keep_places"], doc_like=True).text  # pasted text is masked the same way
    clauses = split_clauses(pseudo)
    if not clauses:
        raise ValueError("no clause found: the text is too short")
    passages: dict[str, Any] = {}
    per_clause: dict[int, list[str]] = {}
    for c in clauses:
        res = ctx.engine.retrieve(RetrievalRequest(query=c["text"][:600], as_of=when, today=ctx.today_fn(), lang="ar" if lang == "ar" else lang, expand=False, keep=3, case_id=case_id))
        ids = []
        for cand in res.candidates:
            if cand.score <= 0 and cand.source != "exact":
                continue
            pid = f"P{cand.chunk.chunk_id}"
            passages.setdefault(pid, cand)
            ids.append(pid)
        per_clause[c["n"]] = ids
    sources = {pid: renderer.source_entry(pack, cand, lang, when, pid) for pid, cand in passages.items()}
    # the articles the document itself cites (the text with names masked still holds "المادة 230 من ق.ل.ع")
    cited = []
    for ref in parse_citations(pseudo, pack.aliases(), pack.instrument_ids()):
        pid = pack.find_provision(ref.instrument_id, ref.number, ref.suffix) if ref.instrument_id else None
        ver = pack.version_at(pid, when) if pid else None
        cited.append({"reference": ref.raw, "provision_id": pid, "in_force_on_date": bool(ver),
                      "text": (pack.texts(ver["pv_id"]).get("ar") or {}).get("text") if ver else None,
                      "note": None if ver else ("article not in the pack" if not pid else f"no text in force on {when.isoformat()}")})
    out: dict[str, Any] = {"doc_id": doc_id, "as_of": when.isoformat(), "clauses": [{**c, "passages": per_clause[c["n"]]} for c in clauses], "passages": sources,
                           "cited_in_document": cited, "findings": [], "status": "retrieved_only", "notice": DISCLAIMER.get(lang, DISCLAIMER["en"]),
                           "pack": {"version": pack.version}}
    llm = ctx.llm()
    if llm is None:
        out["note"] = "no language model in this mode: the clauses are shown with the articles found, without a verdict"
        return out
    payload = {"language": lang, "date": when.isoformat(),
               "clauses": [{"n": c["n"], "text": c["text"]} for c in clauses if per_clause[c["n"]]],
               "passages": [{"id": pid, "source": f"{s['law']} - {s['article']}", "text": s["text"]} for pid, s in sources.items()]}
    try:
        got = llm.generate_json(GenRequest(SYSTEM, payload, SCHEMA, [c["text"] for c in clauses], case_id, kind="contract_check"))
    except Exception as e:  # noqa: BLE001 - provider errors, blocked sends: the retrieval result is still useful
        out["note"] = f"the model was not used ({e.__class__.__name__}): the clauses are shown with the articles found"
        return out
    kept, dropped = [], 0
    for f in got.get("findings") or []:
        s = sources.get(f.get("passage"))
        n = f.get("clause")
        if not s or n not in per_clause or f.get("passage") not in per_clause[n] or not _quote_in(f.get("quote", ""), s["text"]):
            dropped += 1  # a finding whose quote is not in its article is thrown away, never shown
            continue
        kept.append({"clause": n, "verdict": f["verdict"], "why": ctx.pseudo.restore(f.get("why", ""), case_id)[0] if case_id else f.get("why", ""),
                     "quote": f["quote"], "provision_id": s["provision_id"], "law": s["law"], "article": s["article"], "trust": s["trust"], "valid_from": s["valid_from"]})
    order = {"conflicts": 0, "check": 1, "consistent": 2}
    kept.sort(key=lambda f: (order[f["verdict"]], f["clause"]))
    out.update(findings=kept, status="checked", findings_dropped_unverified=dropped,
               summary={v: sum(1 for f in kept if f["verdict"] == v) for v in order})
    return out


# ------------------------------------------------------------------------------------------------ guides from the pack
GUIDE_SYSTEM = """You turn Moroccan law articles into a short checklist for ordinary people. Use ONLY the numbered passages. Give 3-8 steps; each step: a short title,
one or two sentences saying what the law provides (deadlines, conditions, documents, who to go to, only if a passage says so), and the ids of the passages it rests on.
Never invent a number, deadline or office. If the passages do not cover something, leave it out. Write in the reader's language."""
GUIDE_SCHEMA = {"type": "object", "properties": {"steps": {"type": "array", "items": {"type": "object", "properties": {
    "title": {"type": "string"}, "text": {"type": "string"}, "passages": {"type": "array", "items": {"type": "string"}}}, "required": ["title", "text", "passages"]}}},
    "required": ["steps"]}

_GUIDE_CACHE: dict[tuple, dict[str, Any]] = {}


def build_guide(ctx: AppContext, topic: str, queries: list[str], as_of: date | None, lang: str, label: str | None = None) -> dict[str, Any]:
    pack = ctx.pack
    assert pack is not None
    when = as_of or ctx.today_fn()
    llm = ctx.llm()
    key = (pack.version, str(pack.path), topic, tuple(queries), when.isoformat(), lang, llm.model if llm else None)
    if key in _GUIDE_CACHE:
        return {**_GUIDE_CACHE[key], "cached": True}
    seen, srcs = set(), {}
    for q in queries or [topic]:
        res = ctx.engine.retrieve(RetrievalRequest(query=q, as_of=when, today=ctx.today_fn(), lang=lang, expand=False, keep=6))
        for c in res.candidates:
            if c.score > 0 and c.chunk.provision_id not in seen:
                seen.add(c.chunk.provision_id)
                srcs[f"P{c.chunk.chunk_id}"] = renderer.source_entry(pack, c, lang, when, f"P{c.chunk.chunk_id}")
    out: dict[str, Any] = {"topic": topic, "label": label, "as_of": when.isoformat(), "articles": list(srcs.values()), "steps": [], "status": "articles_only",
                           "notice": renderer.DISCLAIMER[renderer.L(lang)], "pack": {"version": pack.version}, "cached": False}
    if llm is not None and srcs:
        try:
            got = llm.generate_json(GenRequest(GUIDE_SYSTEM, {"language": lang, "situation": label or topic, "date": when.isoformat(),
                                                             "passages": [{"id": k, "source": f"{s['law']} - {s['article']}", "text": s["text"][:1800]} for k, s in srcs.items()]},
                                               GUIDE_SCHEMA, [], None, kind="guide"))
            steps = []
            for st in got.get("steps") or []:
                ids = [p for p in st.get("passages", []) if p in srcs]
                if ids and st.get("title") and st.get("text"):  # a step with no real article behind it is dropped
                    steps.append({"title": st["title"], "text": st["text"], "articles": [{"id": p, "provision_id": srcs[p]["provision_id"], "law": srcs[p]["law"], "article": srcs[p]["article"]} for p in ids]})
            out.update(steps=steps, status="generated" if steps else "articles_only")
        except Exception as e:  # noqa: BLE001
            out["note"] = f"the model was not used ({e.__class__.__name__}): the articles are listed without steps"
    if len(_GUIDE_CACHE) > 64:
        _GUIDE_CACHE.clear()
    if out["status"] == "generated" or llm is None:
        _GUIDE_CACHE[key] = out
    return out
