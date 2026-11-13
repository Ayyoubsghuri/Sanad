"""Retrieval engine: exact lookup -> hybrid (BM25 + dense, RRF) -> rerank -> authority order -> graph expansion -> coverage.

Everything that touches the user's words receives PSEUDONYMISED text only. Dense search and reranking may run
locally or in the cloud depending on the operating mode; keyword search never depends on the cloud, and every
cloud failure degrades to keyword search + the lexical reranker instead of failing.
"""
from __future__ import annotations

import re

import time
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from ..config import Settings
from ..services import terms as terms_svc
from ..store.lawpack import ChunkMeta, LawPack
from ..text import stopwords
from ..text.arabic import light_stem, tokens
from ..text.citations import CitationRef
from .rerankers import LexicalReranker, Reranker


SUBQ_QUOTA = 3  # passages each sub-question keeps for itself
SUBQ_MIN_SCORE = 0.25
SUBQ_POOL = 12  # best passages of each sub-question that always reach the reranker
PRIMARY_KINDS = ("constitution", "organic_law", "treaty", "law", "dahir_law", "code")  # the law itself, not the orders that apply it


@dataclass
class Candidate:
    chunk: ChunkMeta
    source: str  # exact | search | graph | definition | transitional | prior_version
    dense_rank: int | None = None
    bm25_rank: int | None = None
    rrf: float = 0.0
    score: float = 0.0  # reranker score 0..1 (1.0 for exact hits)
    via: str | None = None  # provision_id that pulled this in (graph/definition/transitional)
    note: str | None = None


@dataclass
class Coverage:
    top_score: float = 0.0
    margin: float = 0.0
    supports: int = 0
    exact_hits: int = 0
    covered: bool = False
    reason: str | None = None
    broad: bool = False  # an open "how do I" question: no single article answers it, so the reranker scores are all low and the passages were picked by search rank


@dataclass
class RetrievalRequest:
    query: str
    as_of: date
    sub_questions: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    exact_refs: list[CitationRef] = field(default_factory=list)
    facts_date: date | None = None
    today: date = field(default_factory=date.today)
    lang: str = "ar"
    case_id: str | None = None
    show_both_versions: bool = False
    expand: bool = True
    weak_device: bool = False
    keep: int | None = None
    focus_instruments: list[str] = field(default_factory=list)  # laws the question names by number: search inside them first


@dataclass
class RetrievalResult:
    candidates: list[Candidate]
    coverage: Coverage
    notes: list[str] = field(default_factory=list)  # fallbacks / warnings shown to the user
    unresolved_refs: list[dict] = field(default_factory=list)
    timings_ms: dict[str, int] = field(default_factory=dict)
    modes_used: dict[str, str] = field(default_factory=dict)  # embedder / reranker actually used
    focus_chunk_ids: set[int] = field(default_factory=set)  # passages of the laws the question names by number
    pool_extra: int = 0  # passages added to the rerank pool because a sub-question ranked them high on its own

    def chunk_ids(self) -> list[int]:
        return [c.chunk.chunk_id for c in self.candidates]


def build_fts_query(query_tokens: list[str], extra: list[str] | None = None, max_terms: int = 24) -> str:
    seen, terms = set(), []
    for t in [*query_tokens, *(extra or [])]:
        t = light_stem(t)
        if t in stopwords.ALL or len(t) < 2 or t in seen:
            continue
        seen.add(t)
        terms.append(t)
    return " OR ".join('"' + t.replace('"', "") + '"' for t in terms[:max_terms])


def rrf_fuse(rank_lists: list[list[int]], k: int) -> dict[int, float]:
    scores: dict[int, float] = {}
    for lst in rank_lists:
        for rank, cid in enumerate(lst, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    return scores


class RetrievalEngine:
    def __init__(
        self,
        pack: LawPack,
        settings: Settings,
        embedder_getter: Callable[[], object | None],
        reranker_getter: Callable[[], Reranker | None],
    ):
        self.pack, self.s = pack, settings
        self._embedder_getter, self._reranker_getter = embedder_getter, reranker_getter
        self._lexical = LexicalReranker()

    # ------------------------------------------------------------------------------------------------
    def retrieve(self, req: RetrievalRequest) -> RetrievalResult:
        t0 = time.monotonic()
        res = RetrievalResult([], Coverage())
        tm = res.timings_ms
        selected: dict[int, Candidate] = {}

        # 1. exact references: plain lookup, no search ---------------------------------------------------
        for ref in req.exact_refs:
            self._exact(ref, req, selected, res)
        res.coverage.exact_hits = sum(1 for c in selected.values() if c.source == "exact")
        tm["exact"] = int((time.monotonic() - t0) * 1000)

        # 2-4. hybrid retrieval -----------------------------------------------------------------------------
        t1 = time.monotonic()
        search_cands = self._hybrid(req, res)
        tm["hybrid"] = int((time.monotonic() - t1) * 1000)

        # 5. rerank ---------------------------------------------------------------------------------------------
        t2 = time.monotonic()
        keep = req.keep or (self.s.rerank_keep_weak if req.weak_device else self.s.rerank_keep)
        n_in = self.s.rerank_in_weak if req.weak_device else self.s.rerank_in
        search_cands = search_cands[:n_in + res.pool_extra]
        per_q = self._rerank(req, search_cands, res)
        search_cands_before_sort = list(search_cands)  # the per-sub-question scores are in this order
        if res.focus_chunk_ids:  # the user named this law: a passage inside it is in scope even when few words match
            for c in search_cands:
                if c.chunk.chunk_id in res.focus_chunk_ids and c.score > 0:
                    c.score = min(1.0, c.score + self.s.focus_bonus)
        # an AMENDING law's article quotes the new wording of a code ("تنسخ وتعوض على النحو التالي أحكام ... «المادة 78-1 ...»"): when the code's
        # own article is also found, the code is what a lawyer cites, so the amending text steps back (it stays as a source)
        if any(not _AMENDING.match(c.chunk.body or "") for c in search_cands if c.score > 0):
            for c in search_cands:
                if _AMENDING.match(c.chunk.body or ""):
                    c.score *= 0.8
        search_cands.sort(key=lambda c: -c.score)
        tm["rerank"] = int((time.monotonic() - t2) * 1000)

        # 6. coverage (on search candidates only; exact hits are covered by construction) -----------------------------
        res.coverage = self._coverage(search_cands, res.coverage.exact_hits)
        broad = self._broad_pool(req, search_cands, res.coverage)
        if broad:
            res.coverage.covered, res.coverage.reason, res.coverage.broad = True, None, True
            res.notes.append("broad question: no single article answers it, so the passages were chosen by search rank, not by reranker score")
        if not res.coverage.covered and any(c.source == "prior_version" for c in selected.values()):
            # the user cited an article that has ended: answer with its history (and the rule in force if the search found it)
            res.coverage.covered, res.coverage.reason = True, None

        for c in search_cands[:keep]:
            if c.score > 0 and c.chunk.pv_id not in {x.chunk.pv_id for x in selected.values()}:
                selected[c.chunk.chunk_id] = c
        if broad:
            have_pv = {x.chunk.pv_id for x in selected.values()}
            for c in broad:
                if c.chunk.pv_id not in have_pv:
                    selected[c.chunk.chunk_id] = c
                    have_pv.add(c.chunk.pv_id)
        # every sub-question keeps its own best passages: in a story with several issues, the most talked-about one must not crowd the others out
        if per_q and len(per_q[0]) == len(search_cands_before_sort):
            have_pv = {x.chunk.pv_id for x in selected.values()}
            for qs in per_q:
                ranked = sorted(range(len(qs)), key=lambda i: -qs[i])
                taken = 0
                for i in ranked:
                    if taken >= SUBQ_QUOTA or qs[i] < SUBQ_MIN_SCORE:
                        break
                    c = search_cands_before_sort[i]
                    if c.chunk.pv_id in have_pv:
                        taken += 1
                        continue
                    selected[c.chunk.chunk_id] = c
                    have_pv.add(c.chunk.pv_id)
                    taken += 1
        cands = list(selected.values())
        cands = self._drop_amending_copies(cands, res)

        # 7. authority order (presentation order of the SELECTED set) -----------------------------------------------------
        cands = self._authority_order(cands)
        if res.focus_chunk_ids:
            cands.sort(key=lambda c: c.chunk.chunk_id not in res.focus_chunk_ids)  # stable: the named law first

        # 8. graph / definitions / transitional / prior versions ------------------------------------------------------------------
        if req.expand and cands:
            t3 = time.monotonic()
            cands += self._expand(req, cands, res)
            tm["expand"] = int((time.monotonic() - t3) * 1000)
        if req.show_both_versions:
            cands += self._prior_versions(req, cands)

        res.candidates = cands
        tm["total"] = int((time.monotonic() - t0) * 1000)
        return res

    @staticmethod
    def _drop_amending_copies(cands: list[Candidate], res: RetrievalResult) -> list[Candidate]:
        """An amending law quotes the new wording of a code article ("تنسخ وتعوض ... «المادة 78-2. - يحدد أجل ..."). When that code article,
        in force on the date, was found too, the copy inside the amending law is dropped: the answer cites the code, not the law that changed it."""
        from ..text.arabic import normalize as _norm

        def key(t: str) -> str:
            return re.sub(r"[^\w]", "", _norm(t or ""))

        codes = [key(c.chunk.body) for c in cands if not _AMENDING.match(c.chunk.body or "")]
        codes = [k for k in codes if len(k) >= 60]
        if not codes:
            return cands
        out = []
        for c in cands:
            if c.source != "exact" and _AMENDING.match(c.chunk.body or ""):
                body = key(c.chunk.body)
                if any(sum(1 for w in range(0, min(len(k), 400), 50) if k[w:w + 40] in body) >= 2 for k in codes):
                    res.notes.append(f"{c.chunk.provision_id}: amending text left out, the article of the code in force says the same")
                    continue
            out.append(c)
        return out

    # ------------------------------------------------------------------------------------------------------
    def _lang_pick(self, pv_id: int, lang: str) -> list[ChunkMeta]:
        chunks = self.pack.chunks_for_pv(pv_id)
        if not chunks:
            return []
        for want in (lang, chunks[0].controlling_lang, "ar", "fr"):
            pick = [c for c in chunks if c.lang == want]
            if pick:
                return pick
        return chunks[:1]

    def _exact(self, ref: CitationRef, req: RetrievalRequest, selected: dict[int, Candidate], res: RetrievalResult) -> None:
        if not ref.instrument_id:
            res.unresolved_refs.append({"raw": ref.raw, "reason": "law_not_identified"})
            return
        pid = self.pack.find_provision(ref.instrument_id, ref.number, ref.suffix)
        ver = self.pack.version_at(pid, req.as_of) if pid else None
        if not ver:
            # a newer consolidated edition of the same law is filed as its own instrument ("LAW_22.01_2025"): a citation of the law
            # by name or number goes to whichever edition is in force on the date
            for sib in sorted((i for i in self.pack.instrument_ids() if i.startswith(ref.instrument_id + "_")), reverse=True):
                spid = self.pack.find_provision(sib, ref.number, ref.suffix)
                sver = self.pack.version_at(spid, req.as_of) if spid else None
                if sver:
                    pid, ver = spid, sver
                    break
        if not ver:
            from ..store.lawpack import SUCCESSORS

            succ = SUCCESSORS.get(ref.instrument_id)
            if succ and not ref.raw.lstrip().startswith("الفصل"):
                ids = self.pack.instrument_ids()
                for iid2 in [succ, *sorted((i for i in ids if i.startswith(succ + "_")), reverse=True)]:
                    spid = self.pack.find_provision(iid2, ref.number, ref.suffix) if iid2 in ids else None
                    sver = self.pack.version_at(spid, req.as_of) if spid else None
                    if sver:
                        pid, ver = spid, sver
                        res.notes.append(f"{ref.raw}: the code it names was replaced by {succ.split('_', 1)[1]}; the article of the law in force is used")
                        break
        if not pid:
            res.unresolved_refs.append({"raw": ref.raw, "reason": "article_not_in_pack", "instrument_id": ref.instrument_id})
            return
        if not ver:
            all_v = self.pack.versions(pid)
            res.unresolved_refs.append(
                {"raw": ref.raw, "reason": "no_trusted_version_on_date", "provision_id": pid,
                 "versions": [{"valid_from": v["valid_from"], "valid_to": v["valid_to"], "status": v["verification_status"]} for v in all_v]}
            )
            # the article was repealed or replaced before the date ("الفصل 440 من ق.م.م" after the new code): show its last text, labelled
            # with the day it ended, and search the law in force for the same rule (its text becomes a search query)
            ended = [v for v in all_v if v.get("valid_to") and v["valid_to"] <= req.as_of.isoformat()]
            if ended:
                last = max(ended, key=lambda v: v["valid_to"])
                chunks = self._lang_pick(last["pv_id"], req.lang)
                for ch in chunks:
                    selected[ch.chunk_id] = Candidate(ch, "prior_version", score=0.0, via=pid,
                                                      note=f"{ref.raw}: text that ended on {last['valid_to']}, not in force on {req.as_of.isoformat()}")
                body = " ".join(ch.body for ch in chunks)[:400]
                if body:
                    req.sub_questions = [body, *req.sub_questions]
                res.notes.append(f"{ref.raw} ended on {last['valid_to']}: its last text is shown, and the law in force was searched for the same rule")
            return
        for ch in self._lang_pick(ver["pv_id"], req.lang):
            selected[ch.chunk_id] = Candidate(ch, "exact", score=1.0, note=f"exact reference: {ref.raw}")

    # ------------------------------------------------------------------------------------------------------
    def _hybrid(self, req: RetrievalRequest, res: RetrievalResult) -> list[Candidate]:
        queries = [req.query] + [q for q in req.sub_questions if q and q != req.query][: self.s.max_subquestions]
        extra, _doms = terms_svc.expand_terms(req.query)
        bm25_lists: list[list[int]] = []
        for q in queries:
            fts = build_fts_query(tokens(q), extra if q is req.query else None)
            bm25_lists.append([cid for cid, _ in self.pack.keyword_search(fts, req.as_of, self.s.bm25_k)])
        dense_lists: list[list[int]] = []
        qvecs = None
        res.modes_used["keyword"] = "local"
        emb = self._embedder_getter()
        if emb is None:
            res.notes.append("dense search unavailable (no embedder for this mode): keyword search only")
            res.modes_used["embedder"] = "none"
        elif emb.embedder_id not in self.pack.embedders():
            res.notes.append(f"embedder '{emb.embedder_id}' does not match the law pack's vectors: keyword search only")
            res.modes_used["embedder"] = "mismatch"
        else:
            idx = self.pack.vector_index(emb.embedder_id)
            try:
                vecs = qvecs = emb.embed(queries, req.case_id)
                for v in vecs:
                    dense_lists.append([cid for cid, _ in idx.search(v, req.as_of, self.s.dense_k)])
                res.modes_used["embedder"] = f"{emb.location}:{emb.embedder_id}"
            except Exception as e:  # CloudUnavailable / ModeForbids / OutboundBlocked / local model errors: degrade, never fail
                res.notes.append(f"embedder unreachable ({e.__class__.__name__}): keyword search only")
                res.modes_used["embedder"] = "unreachable"
        fused = rrf_fuse(bm25_lists + dense_lists, self.s.rrf_k)
        focus_ids: set[int] = set()
        if req.focus_instruments:  # "المرسوم 2.25.966 ...": the decree's own passages compete first, even if the search did not rank them high
            focus_ids = set(self.pack.instrument_chunk_ids(req.focus_instruments, req.as_of))
            res.focus_chunk_ids = focus_ids
            floor = min(fused.values(), default=0.0) * 0.5
            for cid in focus_ids:
                fused.setdefault(cid, floor)
        if not fused:
            return []
        top = sorted(fused.items(), key=lambda kv: -(kv[1] + (1.0 if kv[0] in focus_ids else 0.0)))[: max(self.s.rerank_in, 50) * 2]
        # every sub-question also brings ITS OWN best passages into the pool: fusing all lists together favours what many questions share
        # (the wife), and the daughter's article, strong only for her own question, can fall outside the pool
        if len(queries) > 1:
            in_top = {cid for cid, _ in top}
            for i in range(1, len(queries)):
                own = [bm25_lists[i]] + ([dense_lists[i]] if i < len(dense_lists) else [])
                for cid, sc in sorted(rrf_fuse(own, self.s.rrf_k).items(), key=lambda kv: -kv[1])[:SUBQ_POOL]:
                    if cid not in in_top:
                        top.append((cid, fused.get(cid, sc)))
                        in_top.add(cid)
                        res.pool_extra += 1
        # a general question ("working hours") finds thousands of near-identical ministerial orders before it finds the Code: the best passages of
        # LAWS AND CODES alone always join the pool, so the reranker (not the pool limit) decides between a law and an order
        if self.s.primary_pool > 0 and top:
            plists: list[list[int]] = [[cid for cid, _ in self.pack.keyword_search(build_fts_query(tokens(req.query), extra), req.as_of, self.s.primary_k, PRIMARY_KINDS)]]
            if qvecs is not None and emb is not None:
                try:
                    allow = self.pack.kind_mask(emb.embedder_id, PRIMARY_KINDS)
                    plists.append([cid for cid, _ in idx.search(qvecs[0], req.as_of, self.s.primary_k, allow=allow)])
                except Exception:  # noqa: BLE001 - the extra pass must never break the search
                    pass
            in_top = {cid for cid, _ in top}
            cap = top[0][1]
            for cid, sc in sorted(rrf_fuse(plists, self.s.rrf_k).items(), key=lambda kv: -kv[1])[: self.s.primary_pool]:
                if cid not in in_top:
                    top.append((cid, min(cap, max(fused.get(cid, 0.0), sc))))
                    in_top.add(cid)
                    res.pool_extra += 1
        chunks = self.pack.chunks([cid for cid, _ in top])
        dense_rank = {cid: r for lst in dense_lists[:1] for r, cid in enumerate(lst, 1)}
        bm25_rank = {cid: r for lst in bm25_lists[:1] for r, cid in enumerate(lst, 1)}
        mx = top[0][1] or 1.0
        out: list[Candidate] = []
        for cid, sc in top:
            ch = chunks.get(cid)
            if not ch:
                continue
            boost = self.s.domain_boost if self._domain_match(ch, req.domains) else 0.0
            out.append(Candidate(ch, "search", dense_rank.get(cid), bm25_rank.get(cid), rrf=sc / mx + boost + (1.0 if cid in focus_ids else 0.0)))
        out.sort(key=lambda c: -c.rrf)
        return out

    def _domain_match(self, ch: ChunkMeta, domains: list[str]) -> bool:
        if not domains:
            return False
        inst = self.pack.instrument(ch.instrument_id)
        return bool(inst and inst.get("domain") in domains)  # a BOOST, not a filter: a misrouted question still finds its law

    # ------------------------------------------------------------------------------------------------------
    def _rerank(self, req: RetrievalRequest, cands: list[Candidate], res: RetrievalResult) -> list[list[float]]:
        """Scores `cands` in place; returns each sub-question's own scores (same order as `cands`)."""
        if not cands:
            return []
        passages = [c.chunk.body for c in cands]
        rr = self._reranker_getter()
        scores: list[float] | None = None
        if rr is not None and rr.name != "lexical":
            try:
                scores = rr.score(req.query, passages, req.case_id)
                res.modes_used["reranker"] = f"{rr.location}:{rr.name}"
            except Exception as e:  # cloud/local reranker failure -> lexical fallback
                res.notes.append(f"reranker unavailable ({e.__class__.__name__}): lexical ranking used")
        if scores is None:
            scores = self._lexical.score(req.query, passages)
            res.modes_used.setdefault("reranker", "local:lexical")
        # sub-questions: a passage may answer any of them, keep its best score
        per_q: list[list[float]] = []
        for q in req.sub_questions[: self.s.max_subquestions]:
            if q and q != req.query:
                real = rr is not None and rr.name != "lexical" and res.modes_used.get("reranker", "").endswith(rr.name)
                try:  # the real reranker scores each sub-question too (a long story alone scores every passage low); never mix its scale with the lexical one
                    alt = rr.score(q, passages, req.case_id) if real else self._lexical.score(q, passages)
                except Exception:  # noqa: BLE001
                    continue
                per_q.append([float(x) for x in alt])
                scores = [max(a, b) for a, b in zip(scores, alt)]
        for c, s in zip(cands, scores):
            c.score = float(s)
        return per_q

    def _broad_pool(self, req: RetrievalRequest, cands: list[Candidate], cov: Coverage) -> list[Candidate]:
        """An open question ("how do I ask for a divorce?") is answered by many articles, none of them whole, so the reranker scores every one low
        and the gate says "no answer". When the domain is known, the reranker is flat (at most 3 passages above a low floor) and many passages of that
        domain are found by BOTH the dense and the keyword search, pick them by search rank instead. A question the law does not cover has no such
        agreement, so it still gets "no answer"."""
        if not self.s.broad_mode or cov.exact_hits or cov.covered or not req.domains or not cands:
            return []
        floor = self.s.coverage_min_top_score * 0.2
        if sum(1 for c in cands if c.score >= floor) > 3:
            return []
        inside = [c for c in cands if self._domain_match(c.chunk, req.domains)]
        agree = [c for c in inside if c.dense_rank and c.dense_rank <= 30 and c.bm25_rank and c.bm25_rank <= 50]
        if len(agree) < self.s.broad_min_agree:  # a question the law does not cover has no such agreement
            return []
        # once the question is known to be a real one, the keyword search's strong hits of the same domain join (the grounds of a divorce for cause
        # are worded differently from "how do I ask for a divorce", so the meaning search ranks them low)
        keyword = [c for c in inside if c.bm25_rank and c.bm25_rank <= 25 and c not in agree]
        pool = sorted(agree, key=lambda c: -c.rrf)[: self.s.broad_keep - 4] + sorted(keyword, key=lambda c: -c.rrf)[:4]
        return pool[: self.s.broad_keep]

    def _coverage(self, cands: list[Candidate], exact_hits: int) -> Coverage:
        cov = Coverage(exact_hits=exact_hits)
        by_prov: dict[str, float] = {}
        for c in cands:
            by_prov[c.chunk.provision_id] = max(by_prov.get(c.chunk.provision_id, 0.0), c.score)
        ranked = sorted(by_prov.values(), reverse=True)
        if ranked:
            cov.top_score = ranked[0]
            cov.margin = ranked[0] - ranked[1] if len(ranked) > 1 else ranked[0]
            cov.supports = sum(1 for s in ranked if s >= self.s.coverage_min_top_score * 0.8)
        if exact_hits:
            cov.covered = True
        elif not ranked:
            cov.reason = "no provision valid on the as-of date matched the question"
        elif cov.top_score < self.s.coverage_min_top_score:
            cov.reason = f"best match score {cov.top_score:.2f} is below the threshold {self.s.coverage_min_top_score:.2f}"
        elif cov.margin < self.s.coverage_min_margin:
            cov.reason = "the best match is not clearly better than the next candidate"
        elif cov.supports < self.s.coverage_min_supports:
            cov.reason = "too few independent supporting provisions"
        else:
            cov.covered = True
        return cov

    @staticmethod
    def _authority_order(cands: list[Candidate]) -> list[Candidate]:
        # Constitution > organic law > law > decree > order > circular > guidance > court decision;
        # within a rank: higher relevance first, then later (more recent) version first.
        return sorted(cands, key=lambda c: (c.chunk.authority_rank, -c.score, _neg_date(c.chunk.valid_from)))

    # ------------------------------------------------------------------------------------------------------
    def _expand(self, req: RetrievalRequest, cands: list[Candidate], res: RetrievalResult) -> list[Candidate]:
        have_pv = {c.chunk.pv_id for c in cands}
        budget = self.s.graph_budget_tokens
        added: list[Candidate] = []

        def add(pv_id: int, source: str, via: str, note: str) -> bool:
            nonlocal budget
            if pv_id in have_pv:
                return False
            chunks = self._lang_pick(pv_id, req.lang)
            cost = sum(max(1, len(c.body) // 3) for c in chunks)
            if not chunks or cost > budget:
                return False
            budget -= cost
            have_pv.add(pv_id)
            for ch in chunks:
                added.append(Candidate(ch, source, score=0.0, via=via, note=note))
            return True

        # typed edges: one hop by default, two hops only through strong refers_to links
        frontier = [(c.chunk.provision_id, 1) for c in cands[:6]]
        while frontier and budget > 0:
            pid, hop = frontier.pop(0)
            for e in self.pack.edges_from("provision", pid):
                if e["type"] != "refers_to" or e["to_kind"] != "provision" or e["confidence"] < 0.6:
                    continue
                ver = self.pack.version_at(e["to_id"], req.as_of)
                if ver and add(ver["pv_id"], "graph", pid, f"cited by {pid}"):
                    if hop == 1 and e["confidence"] >= 0.85:
                        frontier.append((e["to_id"], 2))

        # an article found by the search that cites an article of ANOTHER law by name ("وفقا لما هو منصوص عليه في المادة 53 من مدونة
        # الأسرة"): bring that article too (one hop), so a penalty and the rule it enforces come together
        try:
            aliases, ids = self.pack.aliases(), self.pack.instrument_ids()
        except Exception:  # noqa: BLE001
            aliases, ids = {}, set()
        if aliases or ids:
            from ..text.citations import parse_citations

            for c in [c for c in cands if c.source in ("search", "exact")][:6]:
                for ref in parse_citations(c.chunk.body, aliases, ids):
                    if not ref.instrument_id or ref.instrument_id == c.chunk.instrument_id:
                        continue
                    ver = None
                    for iid2 in [ref.instrument_id, *sorted((i for i in ids if i.startswith(ref.instrument_id + "_")), reverse=True)]:
                        pid = self.pack.find_provision(iid2, ref.number, ref.suffix)
                        ver = self.pack.version_at(pid, req.as_of) if pid else None
                        if ver:
                            break
                    if ver:
                        add(ver["pv_id"], "graph", c.chunk.provision_id, f"cited by {c.chunk.provision_id}")

        # a term the found article only USES and another article of the same law DEFINES ("سن الرشد القانوني" -> article 209):
        # bring the definition (at most 3), so the answer reads the term as the law defines it
        try:
            from ..text.arabic import normalize as _norm

            qn = _norm(req.query)
            n_def = 0
            for c in [c for c in cands if c.source in ("search", "exact")][:6]:
                if n_def >= 3:
                    break
                body = _norm(c.chunk.body)
                for term, pv in self.pack.defined_terms(c.chunk.instrument_id, req.as_of):
                    if pv == c.chunk.pv_id or n_def >= 3:
                        continue
                    tn = _norm(term)
                    if (len(tn) >= 8 or (' ' not in tn and len(tn) >= 5)) and (tn in body or tn in qn) and add(pv, "definition", c.chunk.provision_id, f"defines «{term}»"):
                        n_def += 1
        except Exception:  # noqa: BLE001 - a definition is extra context; never break the search for it
            pass

        instruments = {c.chunk.instrument_id for c in cands}
        for iid in instruments:
            for pv in self.pack.definition_pvs(iid, req.as_of):
                add(pv, "definition", iid, "definition article of the instrument")
            inst = self.pack.instrument(iid)
            eff = _d(inst.get("effective_date")) if inst else None
            start = req.facts_date or req.as_of
            if eff and start < eff <= req.today:
                for pv in self.pack.transitional_pvs(iid, req.as_of) + self.pack.transitional_pvs(iid, req.today):
                    add(pv, "transitional", iid, f"transitional provision: instrument in force from {eff.isoformat()}")
        return added

    def _prior_versions(self, req: RetrievalRequest, cands: list[Candidate]) -> list[Candidate]:
        """User declined to give a date: also show the version that preceded the current one, labelled."""
        out, have = [], {c.chunk.pv_id for c in cands}
        for c in cands:
            if c.source in ("search", "exact"):
                prev = self.pack.version_before(c.chunk.provision_id, c.chunk.valid_from)
                if prev and prev["pv_id"] not in have:
                    have.add(prev["pv_id"])
                    for ch in self._lang_pick(prev["pv_id"], req.lang):
                        out.append(Candidate(ch, "prior_version", via=c.chunk.provision_id, note=f"previous version, valid until {prev['valid_to']}"))
        return out


_AMENDING_RX = re.compile(r"(?:^|[\s.:؛\-–«\"(])(?:تنسخ\s*و\s*تعوض|ينسخ\s*و\s*يعوض|تغير\s*و\s*تتمم|يغير\s*و\s*يتمم|تتمم\s|يتمم\s|تغير\s+على\s+النحو|تضاف\s|يضاف\s|تنسخ\s+[اأ]حكام|تعوض\s+على\s+النحو)")


class _Amending:
    """Is this passage an amending text ("تنسخ وتعوض على النحو التالي ...")?  Read on the normalised first 160 characters, so a leading
    mark, number or heading ("1 -", "«", "المادة الأولى") does not hide it; or a body full of quoted lines («...) with such a verb."""
    @staticmethod
    def match(body: str) -> bool:
        from ..text.arabic import normalize as _n

        head = _n((body or "")[:200])
        head = re.sub(r"^[\s\d\-–.:«\"(]*(?:الماده\s+(?:\d+(?:-\d+)?|ال\S+)\s+)?[\s\d\-–.:«\"(]*", "", head)
        return bool(_AMENDING_RX.match(" " + head[:60]))


_AMENDING = _Amending()


def _neg_date(s: str) -> int:
    d = _d(s)
    return -d.toordinal() if d else 0


def _d(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None
