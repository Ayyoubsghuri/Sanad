"""The query flow, step by step. Retrieved and checked on the device; written in the cloud; nothing reaches the user until the
verifier passes. Any cloud failure degrades to quoted passages instead of failing.

  prepare():  1 pseudonymise -> send preview (stored as a pending query; the raw text is never persisted)
  run():      2 understand  3 pin date  4 check premise  5 exact refs  6-9 retrieve/rerank/authority  10 expand  11 coverage
              12 generate -> verify (retry once) -> abstain/extractive fallback -> restore names -> render -> trace
"""
from __future__ import annotations

import re
import time
import uuid
from datetime import date
from typing import Any

from ..calc.base import CalcError, CalcResult
from ..llm import prompts
from ..llm.providers import GenRequest
from ..privacy.gateway import CloudUnavailable, ModeForbids, OutboundBlocked
from ..privacy.pseudonymiser import find_placeholders
from ..retrieval.engine import Candidate, RetrievalRequest, RetrievalResult
from ..schemas import PrepareRequest, RunRequest
from ..services import documents as docs
from ..services import terms as terms_svc
from ..state import AppContext
from ..text.citations import parse_citations
from ..verify import renderer
from ..verify.checks import VerificationReport, VerifyContext, verify_answer
from . import conversation as conv
from . import nextsteps as NEXT
from . import websearch as WEB
from . import plan as PLAN
from .memory import get_memory
from . import progress as PG
from . import research
from . import searchquery
from . import understand as U

PLANNED_CALLS = {
    "offline": [],
    "hybrid": [{"kind": "generate", "where": "cloud", "sends": "pseudonymised question + public law passages"},
               {"kind": "claim_check", "where": "cloud-or-local", "sends": "each claim with its quote (pseudonymised)"},
               {"kind": "web_search", "where": "DuckDuckGo", "sends": "a short search query from the masked question (only when web research is on)"},
               {"kind": "next_steps", "where": "cloud", "sends": "pseudonymised situation + public law passages (only when you describe your own situation)"}],
    "cloud_assisted": [{"kind": "embed", "where": "cloud", "sends": "pseudonymised question"}, {"kind": "rerank", "where": "cloud", "sends": "pseudonymised question + public law passages"},
                       {"kind": "generate", "where": "cloud", "sends": "pseudonymised question + public law passages"},
                       {"kind": "claim_check", "where": "cloud-or-local", "sends": "each claim with its quote (pseudonymised)"}],
}


def _strict_question(issue: str, facts: list, lang_hint: str = "fr") -> str:
    """Deterministic text from a glossary issue id + typed facts: no free text."""
    entry = next((e for e in terms_svc.glossary() if e["id"] == issue), None)
    if not entry:
        raise ValueError(f"unknown issue id '{issue}'")
    term = (entry["fr"] or entry["en"] or entry["ar"])[0]
    parts = [f"{f.kind}: {f.value}" for f in facts]
    return f"{term}. " + "; ".join(parts)


class QueryPipeline:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx

    # =============================================================================================== prepare
    def prepare(self, req: PrepareRequest) -> dict[str, Any]:
        ctx, db = self.ctx, self.ctx.db
        if not req.question and not req.strict:
            raise ValueError("give a question or a strict-mode input")
        us = ctx.user_settings()
        case_id = db.create_case(case_id=req.case_id) if req.case_id else db.create_case()
        keep_places = us["keep_places"] if req.keep_places is None else req.keep_places
        for t in req.extra_sensitive_terms:
            if req.remember_terms:
                db.add_marked_term(t)
        extra = [(t, "PERSON") for t in req.extra_sensitive_terms]
        strict = bool(req.strict) or (us["strict_mode"] and not req.question)
        # The earlier turns are masked FIRST: a name found there is then also masked in the question (same placeholder).  Masked after
        # the question, it was recorded as private while the question still had it in clear, and the outbound check blocked the send.
        # The app's own previous answers quote public law (ministers, institutions, appointees): only the rules and the names list run on
        # them, not the PII model, which would record "بنك المغرب" as a private organisation and mask it in every later question.
        raw_hist = [h.model_dump() for h in req.history]
        if req.new_topic:  # the user said this question has nothing to do with the chat: no follow-up reading, no earlier turns sent
            raw_hist = []
        elif req.session_id:  # the server's memory of the whole chat; the browser's messages only seed an unknown chat
            raw_hist = get_memory().context(req.session_id, raw_hist)
        hist = conv.clean_history(raw_hist)
        if req.mask:
            for h in hist:
                h["text"] = ctx.pseudo.pseudonymise(h["text"], case_id, keep_places=keep_places, extra_terms=extra, use_ner=h["role"] == "user").text
        if req.strict:
            text = _strict_question(req.strict.issue, req.strict.facts)
            res_text, ents, conf, warns, counts = text, [], 1.0, [], {}
        elif not req.mask:  # chat text is sent as written; only uploaded files are masked (services/documents)
            res_text, ents, conf, counts = req.question or "", [], 1.0, {}
            warns = []
        else:
            r = ctx.pseudo.pseudonymise(req.question or "", case_id, keep_places=keep_places, extra_terms=extra)
            res_text, ents, conf, warns, counts = r.text, r.entities, r.confidence, r.warnings, r.counts
        mode = ctx.mode
        needs_review = conf < ctx.settings.query_min_confidence and mode != "offline"
        qid = uuid.uuid4().hex[:16]
        db.put_pending(qid, case_id, {
            "pseudo": res_text, "options": {"as_of": req.as_of.isoformat() if req.as_of else None, "as_of_declined": req.as_of_declined,
                                            "calculations": [c.model_dump(mode="json") for c in req.calculations], "document_ids": req.document_ids,
                                            "strict": strict, "history": hist, "mask": req.mask, "session_id": req.session_id},
            "confidence": conf, "warnings": warns, "keep_places": keep_places,
        })
        prepared = {
            "query_id": qid, "case_id": case_id, "mode": mode, "pseudonymised_text": res_text,
            "highlights": [{"placeholder": e.placeholder, "kind": e.kind, "start": e.start, "end": e.end} for e in ents],
            "entity_counts": counts, "confidence": conf, "warnings": warns, "requires_review": needs_review,
            "requires_approval": not us["auto_approve_send"], "strict": strict, "planned_outbound_calls": PLANNED_CALLS[mode] if not (mode == "offline" and ctx.offline_provider_id()) else [
                {"kind": "generate", "where": "this computer", "sends": "nothing leaves the computer (local model)"}],
            "note": "Nothing has left the device. Only this pseudonymised text and public law passages can be sent.",
        }
        if needs_review:
            prepared["review_hint"] = "Detection confidence is low. Edit the text or mark missed names, or switch to Offline mode."
        return prepared

    # =============================================================================================== run
    def run(self, query_id: str, req: RunRequest) -> dict[str, Any]:
        ctx, db = self.ctx, self.ctx.db
        got = db.get_pending(query_id)
        if not got:
            raise KeyError("query not found or expired")
        pend, row = got
        case_id = row["case_id"]
        if not req.approved:
            db.execute("DELETE FROM pending_query WHERE query_id=?", (query_id,))
            return {"status": "cancelled", "query_id": query_id}
        if not ctx.pack_usable():
            return {"status": "unavailable", "reason": ctx.pack_error or "no law pack loaded", "notices": []}
        text = pend["pseudo"]
        warnings: list[str] = list(pend["warnings"])
        if not pend["options"].get("mask", True):
            if req.edited_text is not None:
                text = req.edited_text
        elif req.edited_text is not None or req.extra_sensitive_terms:
            base = req.edited_text if req.edited_text is not None else text
            r = ctx.pseudo.pseudonymise(base, case_id, keep_places=pend["keep_places"], extra_terms=[(t, "PERSON") for t in req.extra_sensitive_terms])
            text, pend["confidence"] = r.text, r.confidence
        if pend["confidence"] < ctx.settings.query_min_confidence and ctx.mode != "offline" and not req.review_confirmed:
            return {"status": "review_required", "query_id": query_id, "confidence": pend["confidence"], "pseudonymised_text": text,
                    "reason": "low pseudonymisation confidence: review the text (or use Offline mode) before sending"}
        PG.begin(ctx.progress, query_id)
        self._web = bool(req.web)
        out = self._answer(text, case_id, pend["options"], req, warnings, pend["confidence"])
        db.execute("DELETE FROM pending_query WHERE query_id=?", (query_id,))
        self._remember(pend["options"].get("session_id"), text, out, case_id, pend["options"].get("mask", True))
        return out

    def _remember(self, session_id: str | None, question: str, out: dict[str, Any], case_id: str, mask: bool) -> None:
        if not session_id or out.get("status") not in ("answered", "partial", "extractive_only"):
            return
        claims = out.get("claims") or []
        answer = " ".join(c.get("text", "") for c in claims if c.get("text"))[:3000]
        cited = sorted({x for c in claims for x in c.get("sources", [])})
        try:
            get_memory().add_turn(session_id, question, answer, cited, conv.make_summarizer(self.ctx.llm(), case_id, scan=mask))
        except Exception:  # noqa: BLE001 - memory is a convenience; an answer is never lost because of it
            pass

    # =============================================================================================== core
    def _answer(self, text: str, case_id: str, opts: dict[str, Any], req: RunRequest, warnings: list[str], conf: float) -> dict[str, Any]:
        ctx, s, pack = self.ctx, self.ctx.settings, self.ctx.pack
        assert pack is not None
        t_start = time.monotonic()
        today = ctx.today_fn()
        us = ctx.user_settings()
        mode = ctx.mode
        explicit = date.fromisoformat(opts["as_of"]) if opts.get("as_of") else None
        hist = opts.get("history") or []
        ctx_law = None
        convo: list[dict[str, str]] = []
        if hist:  # a follow-up is understood with the earlier turns: stand-alone question + the law of the previous answer
            ctx_law = conv.law_from_history(text, pack, hist)
            if conv.is_followup(text, hist, has_refs_with_law=ctx_law is None and bool(parse_citations(text, pack.aliases(), pack.instrument_ids()))):
                llm0 = ctx.llm()
                alone = conv.rewrite(llm0, text, hist, case_id, scan=opts.get("mask", True)) if llm0 is not None else None
                text = alone or conv.rule_standalone(text, hist)
                convo = conv.conversation_block(hist)
        pg = PG.current()
        st = pg.start("Understanding the question", "thinking")
        u = U.understand(text, pack, today=today, explicit_as_of=explicit, as_of_declined=opts.get("as_of_declined", False), max_sub=s.max_subquestions, context_instrument=ctx_law)
        if convo and not u.exact_refs and conv.anaphoric(text):  # "explain it simply": go back to the articles of the previous answer
            u.exact_refs = conv.refs_from_cited(hist)
        lang = us.get("explain_language") or ("ar" if u.lang == "darija" else (u.lang if u.lang in ("ar", "fr", "en") else "fr"))
        pg.done(st, f"language: {u.lang} · type: {u.question_type} · law date: {u.as_of.isoformat()} ({u.as_of_source})"
                    + (f"\ndomains: {', '.join(u.domains)}" if u.domains else "") + (f"\nnamed laws: {', '.join(u.focus_instruments)}" if u.focus_instruments else "")
                    + (f"\nsub-questions: {len(u.sub_questions)}" if len(u.sub_questions) > 1 else "") + (f"\nfollow-up rewritten as: {text}" if convo else ""))
        base: dict[str, Any] = {
            "language": lang, "detected_language": u.lang, "question_type": u.question_type, "domains": u.domains, "mode": mode,
            "as_of": u.as_of.isoformat(), "as_of_source": u.as_of_source, "as_of_assumption": u.as_of_assumption,
            "pack": self._pack_info(), "notices": [renderer.DISCLAIMER[renderer.L(lang)], *renderer.referral_notices(u.flags, lang)],
            "premise_warnings": [], "fallbacks": [], "calculators": [], "sources": [], "related": [], "claims": [],
        }
        if age := ctx.pack_age_days():
            if age > s.pack_max_age_days:
                base["notices"].append(f"The law pack is {age} days old: newer laws may exist. Update the law pack.")
        if ctx.pack_trust and not ctx.pack_trust.ok:
            base["notices"].append("The law pack is unsigned (development mode): its authenticity is not verified.")

        # -- clarification ---------------------------------------------------------------------------------------------------
        if u.clarification:
            return self._finish({**base, "status": "needs_clarification", "clarifying_question": u.clarification, "clarification_kind": u.clarification_kind}, case_id, text, None, t_start)
        if "drafting" in u.flags:
            return self._finish({**base, "status": "abstained", "abstain": renderer.abstention("drafting and strategy are out of scope: this tool quotes the law", u.as_of, lang, u.question_type, {}, [])}, case_id, text, None, t_start, u)

        # -- premise check ---------------------------------------------------------------------------------------------------------
        prem = U.check_premises(text, u, pack)
        base["premise_warnings"] = prem

        # -- calculators (numbers come from tools, never from the model) ----------------------------------------------------------------
        calcs: dict[str, CalcResult] = {}
        for i, c in enumerate(opts.get("calculations", []), start=1):
            try:
                calcs[f"K{i}"] = ctx.calcs.run(c["tool"], c["inputs"])  # type: ignore[union-attr]
            except CalcError as e:
                base["calculators"].append({"tool": c["tool"], "status": e.status, "message": e.message, "missing": e.missing})
                if e.status == "needs_input":
                    return self._finish({**base, "status": "needs_input", "needs_input": {"tool": c["tool"], "message": e.message, "missing": e.missing}}, case_id, text, None, t_start, u)
        base["calculators"] += [{"id": k, **r.to_dict(), "status": "ok"} for k, r in calcs.items()]

        # -- plan: a long story holds several legal issues; search each on its own ----------------------------------------------------------
        if PLAN.worth_planning(text) and not u.exact_refs:
            llm_p = ctx.llm()
            if llm_p is not None:
                st_p = pg.start("Planning the search", "memory", "splitting the situation into legal issues")
                planned = PLAN.issues(llm_p, text, case_id, limit=s.max_subquestions, scan=opts.get("mask", True))
                if planned:
                    u.sub_questions = planned
                pg.done(st_p, ("\n".join(planned)) if planned else "one issue: the normal search is used")

        # -- the question as the law words it: Darija / French / English -> formal Arabic, for the SEARCH only ------------------------------------------
        search_text, sub_qs, domains = text, u.sub_questions, u.domains
        if s.query_rewrite and not u.exact_refs and u.lang != "ar":
            llm_q = ctx.llm()
            q_ar = searchquery.to_formal_arabic(llm_q, text, u.lang, case_id, scan=opts.get("mask", True)) if llm_q is not None else None
            if q_ar:
                st_q = pg.start("Putting the question in the language of the law", "translate")
                search_text = q_ar
                sub_qs = list(dict.fromkeys([text, *u.sub_questions]))[: s.max_subquestions]  # the user's own words still take part
                domains = list(dict.fromkeys([*u.domains, *(e["domain"] for e in terms_svc.match_entries(q_ar))]))
                base["search_query"] = q_ar
                pg.done(st_q, q_ar)

        # -- retrieval ---------------------------------------------------------------------------------------------------------------------
        rreq = RetrievalRequest(
            query=search_text, as_of=u.as_of, sub_questions=sub_qs, domains=domains, exact_refs=u.exact_refs, focus_instruments=u.focus_instruments, today=today, lang="ar" if u.lang == "darija" else u.lang,
            case_id=case_id, show_both_versions=bool(opts.get("as_of_declined")), weak_device=bool(us.get("weak_device")),
        )
        st = pg.start("Searching the law", "search", "keyword + vectors + reranker")
        ret = ctx.engine.retrieve(rreq)  # type: ignore[union-attr]
        pg.done(st, f"{len(ret.candidates)} passage(s) kept · best score {ret.coverage.top_score:.2f} · "
                    + ", ".join(f"{k}: {v}" for k, v in ret.modes_used.items()) + f" · {ret.timings_ms.get('total', 0)} ms"
                    + "".join(f"\n{n}" for n in ret.notes[:3]))
        depth = getattr(req, "depth", "normal")
        if depth != "normal":
            llm_r = ctx.llm()
            if llm_r is None:
                ret.notes.append("deep search needs a language model (not available in this mode): the normal search was used")
            else:
                trace = research.run(ctx, llm_r, rreq, ret, depth=depth, lang=lang, scan_question=opts.get("mask", True), pg=pg)
                base["research"] = trace
        base["fallbacks"] += ret.notes
        base["retrieval"] = {"coverage": vars(ret.coverage), "timings_ms": ret.timings_ms, "modes_used": ret.modes_used, "unresolved_references": ret.unresolved_refs,
                             "named_laws": u.focus_instruments, "named_law_passages": len(ret.focus_chunk_ids)}
        passages = {f"C{c.chunk.chunk_id}": c for c in ret.candidates}
        sources = [renderer.source_entry(pack, c, lang, u.as_of, f"C{c.chunk.chunk_id}") for c in ret.candidates]
        main_src = [x for x in sources if x["role"] in ("exact", "search", "prior_version")]
        base["sources"], base["related"] = main_src, [x for x in sources if x["role"] not in ("exact", "search", "prior_version")]
        base["trust_summary"] = self._trust_summary(sources)
        for ref in ret.unresolved_refs:
            if ref["reason"] == "no_trusted_version_on_date":
                base["notices"].append(f"{ref['raw']}: no trusted text version is valid on {u.as_of.isoformat()}. Versions in the pack: " + ", ".join(f"{v['valid_from']}→{v['valid_to'] or 'now'} ({v['status']})" for v in ref["versions"]))
            elif ref["reason"] == "article_not_in_pack":
                base["notices"].append(f"{ref['raw']} is not in the law pack.")

        # -- a month / year was named: did one of the articles FOUND change during it? (never the whole pack: something always changes) --
        if u.period and not opts.get("as_of_declined"):
            p0, p1, prec = u.period
            changed = []
            for x in main_src[:6]:
                for vi, v in enumerate(pack.versions(x["provision_id"])):
                    # a NEW version starts (not the first one: a text published that year is not a change), or a version ends
                    for edge in ((v["valid_from"] if vi > 0 else None), v.get("valid_to")):
                        if edge and p0.isoformat() < edge <= p1.isoformat() and (x["provision_id"], edge) not in changed:
                            changed.append((x["provision_id"], edge))
            if changed and prec == "month":
                return self._finish({**base, "status": "needs_clarification", "clarifying_question": U.msg(U.CLARIFY, "exact_day", lang), "clarification_kind": "exact_day"}, case_id, text, ret, t_start, u)
            if changed:
                base["notices"].append("Changed during the year you mention: " + ", ".join(f"{pid} (changes on {vf})" for pid, vf in changed[:3]) + ". The version in force on the law date is used; give an exact date for another one.")

        # -- coverage / abstention ---------------------------------------------------------------------------------------------------------------
        if not ret.coverage.covered and not calcs:
            ab = renderer.abstention(ret.coverage.reason or "insufficient evidence", u.as_of, lang, u.question_type,
                                     {"as_of": u.as_of.isoformat(), "domains": u.domains, "candidates_considered": len(ret.candidates)}, main_src[:3])
            self._gap(ab["reason"], u, text)
            return self._finish({**base, "status": "abstained", "abstain": ab}, case_id, text, ret, t_start, u)

        # -- generation ------------------------------------------------------------------------------------------------------------------------------
        llm = ctx.llm()
        headers = self._headers(passages)
        payload_base = dict(
            question=text, lang=lang, as_of=u.as_of.isoformat(), sub_questions=u.sub_questions,
            passages=[{"chunk_id": cid, "lang": c.chunk.lang, "role": c.source, "valid_from": c.chunk.valid_from, "valid_to": c.chunk.valid_to,
                       "source": headers.get(cid, ""), "text": c.chunk.body} for cid, c in passages.items()],
            tool_outputs=[{"calc_id": k, "text": r.text()} for k, r in calcs.items()], premise_warnings=prem, doc_excerpts=[], conversation=convo or None,
            question_kind="open_procedure" if ret.coverage.broad else None,
        )
        try:
            if opts.get("document_ids"):
                payload_base["doc_excerpts"] = docs.excerpts(ctx, opts["document_ids"], text)
        except PermissionError as e:
            return self._finish({**base, "status": "review_required", "reason": str(e)}, case_id, text, ret, t_start, u)
        masking = opts.get("mask", True)
        self._unmasked_question = "" if masking else text
        # with masking off the user chose to send his words as written: the residual-name scan is not applied to them (documents still are)
        user_fields = ([text] if masking else []) + [*payload_base["doc_excerpts"]] + ([c["text"] for c in convo] if masking else [])
        if req.preview_payload:
            return {"status": "payload_preview", "payload": prompts.build_payload(**payload_base), "system": prompts.SYSTEM, "schema": prompts.ANSWER_SCHEMA,
                    "model": llm.model if llm else None, "note": "This is exactly what would be sent. Nothing was sent."}

        verdict: dict[str, Any] | None = None
        if llm is None:
            base["fallbacks"].append("no language model in this mode: quoted articles only" if mode == "offline" else "no language model configured: quoted articles only")
        else:
            st = pg.start("Writing the answer from the articles, then checking every quote", "analysis", f"{len(passages)} passage(s) sent · model {llm.model}")
            verdict = self._generate_and_verify(llm, payload_base, user_fields, passages, calcs, case_id, u, base)
            vr = (verdict or {}).get("report")
            pg.done(st, (f"{len(vr.passed_claims)} of {len(vr.claims)} claim(s) verified · {verdict['attempts']} attempt(s)" if vr else "no answer from the model: quoted articles shown"))

        # -- assemble ------------------------------------------------------------------------------------------------------------------------------------------
        if verdict is None:
            self._gap("generation unavailable", u, text) if llm is not None else None
            return self._finish({**base, "status": "extractive_only", "claims": [], "assumptions": [u.as_of_assumption]}, case_id, text, ret, t_start, u)
        out = self._compose(base, verdict, passages, case_id, u, lang, text)
        if out.get("status") in ("answered", "partial") and us.get("next_steps_in_answers", True) and NEXT.is_case(text):
            self._next_steps(out, llm, verdict, passages, headers, calcs, text, case_id, u, lang, masking, pg)
        return self._finish(out, case_id, text, ret, t_start, u, verdict.get("report"))

    # ------------------------------------------------------------------------------------------------------------ generate + verify
    def _generate_and_verify(self, llm, payload_base, user_fields, passages, calcs, case_id, u, base) -> dict[str, Any] | None:
        ctx = self.ctx
        vctx = VerifyContext(passages, calcs, ctx.pseudo.known_placeholders(case_id), u.as_of, u.sub_questions, u.question_numbers, ctx.claim_checker(), case_id,
                             headers=self._headers(passages), question=str(payload_base.get("question") or ""), unmasked_question=getattr(self, "_unmasked_question", ""))
        failures: list[str] | None = None
        best: tuple[dict[str, Any], VerificationReport] | None = None
        for attempt in (1, 2):
            try:
                answer = llm.generate_json(GenRequest(prompts.SYSTEM, prompts.build_payload(**payload_base, prior_failures=failures), prompts.ANSWER_SCHEMA, user_fields, case_id))
            except OutboundBlocked as e:
                base["fallbacks"].append(f"send blocked: residual identifiers detected ({', '.join(e.kinds)}). Review the preview and mark missed names.")
                base["blocked_kinds"] = e.kinds
                return None
            except (CloudUnavailable, ModeForbids, ValueError, KeyError) as e:
                base["fallbacks"].append(f"language model unavailable ({e.__class__.__name__}: {str(e)[:300]}): quoted articles only")
                return None
            except Exception as e:  # noqa: BLE001 - never crash the user's query on a provider error
                base["fallbacks"].append(f"language model error ({e.__class__.__name__}): quoted articles only")
                return None
            if answer.get("clarifying_question") and not answer.get("claims"):
                return {"answer": answer, "report": None, "attempts": attempt, "kind": "clarify"}
            report = verify_answer(answer, vctx)
            best = (answer, report)
            if report.all_ok or not report.claims and answer.get("abstain_reason"):
                break
            failures = report.failure_reasons()[:8]
        assert best is not None
        return {"answer": best[0], "report": best[1], "attempts": attempt, "kind": "answer"}

    def _compose(self, base, verdict, passages, case_id, u, lang, text) -> dict[str, Any]:
        ctx = self.ctx
        answer, report, attempts = verdict["answer"], verdict["report"], verdict["attempts"]
        if verdict["kind"] == "clarify":
            q, _ = ctx.pseudo.restore(answer["clarifying_question"], case_id)
            return {**base, "status": "needs_clarification", "clarifying_question": q, "clarification_kind": "model"}
        ok = report.passed_claims
        assumptions = [u.as_of_assumption, *[a for a in answer.get("assumptions", []) if isinstance(a, str)]]
        claims_out = []
        for c in ok:
            rtext, _ = ctx.pseudo.restore(c.claim["text"], case_id)  # names restored ONLY after every check passed
            claims_out.append({"type": c.claim.get("type"), "text": rtext, "sources": sorted(set(c.cited_chunks)), "calculators": sorted(set(c.cited_calcs)), "verified": True})
        restored_assump = [ctx.pseudo.restore(a, case_id)[0] for a in assumptions]
        out = {**base, "assumptions": restored_assump, "claims": claims_out, "verification": report.summary(), "generation_attempts": attempts}
        if report.unanswered:
            out["unanswered_sub_questions"] = [u.sub_questions[i] for i in report.unanswered]
        if report.global_failures:
            out["notices"] = out["notices"] + ["Two versions of an article apply on different dates; both are shown in the sources with their dates."]
        dropped = len(report.claims) - len(ok)
        if not ok:
            reason = answer.get("abstain_reason")
            out["status"] = "abstained" if reason and not report.claims else "extractive_only"
            out["could_not_verify"] = True
            if reason:
                out["abstain"] = renderer.abstention(ctx.pseudo.restore(reason, case_id)[0], u.as_of, lang, u.question_type, {"as_of": u.as_of.isoformat()}, base["sources"][:3])
                self._gap("model abstained", u, text)
            else:
                self._gap("verification failed", u, text)
            return out
        out["status"] = "answered" if not dropped and not report.unanswered else "partial"
        if dropped or report.unanswered:
            out["could_not_verify"] = True
            out["notices"] = out["notices"] + ["Part of the answer could not be verified and was left out: rely on the quoted articles below."]
        return out

    # ------------------------------------------------------------------------------------------------------------ what to do next
    def _deadline_passages(self, passages, ids, query: str, u, case_id: str) -> dict[str, Candidate]:
        """Articles on time limits and limitation in the same laws as the answer: the most urgent part of a plan, and often
        not among the articles found for the question itself ("how long do I have to sue?")."""
        insts = list(dict.fromkeys(passages[i].chunk.instrument_id for i in ids if i in passages))[:3]
        if not insts or self.ctx.engine is None:
            return {}
        try:
            res = self.ctx.engine.retrieve(RetrievalRequest(
                query=f"{query[:300]} أجل رفع الدعوى التقادم الآجال", as_of=u.as_of, today=self.ctx.today_fn(), lang="ar",
                case_id=case_id, focus_instruments=insts, expand=False, keep=12))
        except Exception:  # noqa: BLE001 - the plan is written without it
            return {}
        out: dict[str, Candidate] = {}
        for c in res.candidates:
            cid = f"C{c.chunk.chunk_id}"
            if cid in passages or c.chunk.instrument_id not in insts or not NEXT.DEADLINE_WORDS.search(c.chunk.body):
                continue
            out[cid] = c
            if len(out) >= 3:
                break
        return out

    def _next_steps(self, out, llm, verdict, passages, headers, calcs, text, case_id, u, lang, masking, pg) -> None:
        """The plan for a personal situation, from the articles of the answer, the articles on time limits, the calculators
        and the similar rulings; names restored after the checks."""
        ctx = self.ctx
        ok = verdict["report"].passed_claims
        cited = [cid for c in ok for cid in c.cited_chunks if cid in passages]
        ids = list(dict.fromkeys([*cited, *passages]))[:10]          # the cited articles first, then the best of the others
        st = pg.start("Working out what you can do next", "analysis", f"from {len(ids)} article(s) of the answer, the time limits and the similar rulings")
        try:
            query = out.get("search_query") or text
            extra = self._deadline_passages(passages, ids, query, u, case_id)
            if extra:   # shown with the sources, so the steps' [n] point at them
                shown = {x["id"] for x in out.get("sources", [])}
                out["sources"] = out.get("sources", []) + [
                    {**renderer.source_entry(ctx.pack, c, lang, u.as_of, cid), "role": "deadline"} for cid, c in extra.items() if cid not in shown]
            heads = {**headers, **self._headers(extra)}
            allp = {**{i: passages[i] for i in ids}, **extra}
            out["rulings"] = out.get("rulings") or (self._rulings(query, out) if ctx.user_settings().get("show_rulings_in_answers", True) else None)
            res = NEXT.build(llm, question=text, lang=lang, as_of=u.as_of.isoformat(), claims=[c.claim["text"] for c in ok],
                             passages={i: {"source": heads.get(i, ""), "text": c.chunk.body} for i, c in allp.items()},
                             calcs=[r.text() for r in calcs.values()], rulings=out["rulings"], case_id=case_id, scan=masking,
                             deadline_ids=list(extra))
        except Exception as e:  # noqa: BLE001 - the steps are an extra: the verified answer is never lost over them
            out["fallbacks"] = out.get("fallbacks", []) + [f"next steps not written ({e.__class__.__name__})"]
            out["next_steps_error"] = e.__class__.__name__
            pg.done(st, "not written: the answer is shown without them")
            return
        if not res:
            pg.done(st, "none: a general question, or no step could be tied to an article")
            return
        R = lambda s: ctx.pseudo.restore(s, case_id)[0] if s else s  # noqa: E731
        for x in res["steps"]:
            x.update(title=R(x["title"]), text=R(x["text"]), deadline=R(x["deadline"]), where=R(x["where"]), documents=[R(d) for d in x["documents"]])
        for x in res["court_insights"]:
            x["text"] = R(x["text"])
        res["to_clarify"] = [R(c) for c in res["to_clarify"]]
        res["professional"] = R(res["professional"])
        out["next_steps"] = res
        pg.done(st, f"{len(res['steps'])} step(s), {len(res['court_insights'])} point(s) from the rulings"
                    + (f", {len(extra)} article(s) on time limits" if extra else "") + ", each checked against its sources")

    # ------------------------------------------------------------------------------------------------------------ helpers
    @staticmethod
    def _answer_articles(out: dict[str, Any]) -> set[str]:
        """The article numbers the answer rests on: the sources its verified claims cite, else the sources shown."""
        cited = {sid for c in out.get("claims") or [] for sid in c.get("sources", [])}
        srcs = [x for x in out.get("sources") or [] if not cited or x.get("id") in cited]
        return {m.group(0) for x in srcs for m in [re.search(r"\d+", str(x.get("article") or ""))] if m}

    def _rulings(self, text: str, out: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Similar Court of Cassation rulings, searched on this computer only (rulings.db, when it is installed)."""
        from ..pro.rulings import open_store, related_for_answer
        try:
            store = open_store(self.ctx.settings.data_dir)
            return related_for_answer(store, text, articles=self._answer_articles(out or {})) if store else None
        except Exception:  # noqa: BLE001 - the rulings are an extra: never fail an answer over them
            return None

    def _headers(self, passages: dict[str, Candidate]) -> dict[str, str]:
        """What a reader sees above an article: the text's title (with its own date and number) and the bulletin that published it.
        Sent with each passage and used by the checks, so "the order of 2 January 2026, BO 7475" can be quoted and verified."""
        pack, out, cache = self.ctx.pack, {}, {}
        for cid, c in passages.items():
            iid = c.chunk.instrument_id
            if iid not in cache:
                i = pack.instrument(iid) or {}
                parts = [(i.get("title_ar") or i.get("title_fr") or iid)[:400]]
                if i.get("bo_number"):
                    parts.append(f"الجريدة الرسمية عدد {i['bo_number']}" + (f" بتاريخ {i['bo_date']}" if i.get("bo_date") else ""))
                cache[iid] = " — ".join(parts)
            out[cid] = cache[iid]
        return out

    def _pack_info(self) -> dict[str, Any]:
        p = self.ctx.pack
        return {"version": p.version, "built_at": p.built_at, "age_days": self.ctx.pack_age_days(), "signature": self.ctx.pack_trust.state if self.ctx.pack_trust else None}

    @staticmethod
    def _trust_summary(sources: list[dict[str, Any]]) -> dict[str, int]:
        out: dict[str, int] = {}
        for x in sources:
            out[x["trust"]] = out.get(x["trust"], 0) + 1
        return out

    def _gap(self, reason: str, u: U.Understanding, text: str) -> None:
        p = self.ctx.pack
        self.ctx.db.log_gap(reason, u.domains[0] if u.domains else None, u.question_type, u.as_of.isoformat(), p.version if p else None, text)

    def _finish(self, out: dict[str, Any], case_id: str, text: str, ret: RetrievalResult | None, t0: float, u: U.Understanding | None = None, report: VerificationReport | None = None) -> dict[str, Any]:
        ctx = self.ctx
        us = ctx.user_settings()
        llm = ctx.llm()
        if out.get("status") in ("answered", "partial", "extractive_only") and us.get("show_rulings_in_answers", True) and "rulings" not in out:
            out["rulings"] = self._rulings(out.get("search_query") or text, out)
        if getattr(self, "_web", False) and out.get("status") in ("answered", "partial", "extractive_only", "abstained"):
            pg = PG.current()
            st = pg.start("Searching official websites", "search", "a short query from the masked question; links only, not used in the answer")
            out["web"] = WEB.run(ctx, out.get("search_query") or text, case_id, client=getattr(self, "web_client", None))
            w = out["web"]
            pg.done(st, f"{len(w.get('results', []))} official page(s)" if "skipped" not in w else f"skipped ({w['skipped']})")
        trace = {
            "status": out["status"], "created_at": None, "pseudonymised_question": text if us["store_question_text"] else None,
            "as_of": out.get("as_of"), "as_of_source": out.get("as_of_source"), "mode": out.get("mode"), "language": out.get("language"),
            "pack_version": out.get("pack", {}).get("version"), "model": llm.model if llm else None, "provider": llm.name if llm else None, "prompt_version": prompts.PROMPT_VERSION,
            "retrieved": [{"chunk_id": s["chunk_id"], "provision_id": s["provision_id"], "valid_from": s["valid_from"], "valid_to": s["valid_to"], "role": s["role"], "trust": s["trust"], "score": s["relevance"]} for s in out.get("sources", []) + out.get("related", [])],
            "retrieval": out.get("retrieval"), "checks": report.summary() if report else None, "claims": out.get("claims"), "calculators": [c.get("tool") for c in out.get("calculators", [])],
            "fallbacks": out.get("fallbacks"), "elapsed_ms": int((time.monotonic() - t0) * 1000), "sources_snapshot": out.get("sources"), "assumptions": out.get("assumptions"),
            "premise_warnings": out.get("premise_warnings"), "notices": out.get("notices"),
            "sub_questions": list(u.sub_questions) if u else None, "research": out.get("research"),
            "all_claims": [{"index": c.index, "passed": c.passed, "type": c.claim.get("type"), "text": c.claim.get("text"),
                            "support": c.claim.get("support"), "failures": [f"[{f.check}] {f.reason}" for f in c.failures]} for c in report.claims] if report else None,
        }
        out["trace_id"] = ctx.db.put_trace(trace, case_id)
        steps = PG.current().finish()
        if steps:
            out["steps"] = steps
        return out
