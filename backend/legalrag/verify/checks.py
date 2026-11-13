"""Verification in code, after generation. The model proposes; this module decides what ships.

Checks, in order (blueprint table): citation exists -> quote matches -> placeholders intact -> version is right ->
no stray numbers -> claim is supported (independent checker) -> all sub-questions answered -> conflicts are shown.
Scope/risk referrals are added deterministically by the renderer."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..calc.base import CalcResult
from ..llm.providers import ClaimChecker, ClaimItem
from ..privacy import names as N
from ..privacy.patterns import DIRECT_IDENTIFIER_KINDS, detect_patterns
from ..privacy.pseudonymiser import find_placeholders
from ..retrieval.engine import Candidate
from ..store.schema_sql import TRUSTED_STATUSES
from ..text.arabic import normalize, numbers_in, quote_in, tokens

# number words (value >= 2 only: "un"/"one"/"واحد" are articles/pronouns too often)
_WORDS: dict[str, int] = {}
for _val, _ws in {
    2: "deux two اثنان اثنين", 3: "trois three ثلاثة ثلاث", 4: "quatre four اربعة اربع", 5: "cinq five خمسة خمس", 6: "six ستة ست", 7: "sept seven سبعة سبع",
    8: "huit eight ثمانية ثمان", 9: "neuf nine تسعة تسع", 10: "dix ten عشرة عشر", 15: "quinze fifteen", 20: "vingt twenty عشرين", 30: "trente thirty ثلاثين",
    40: "quarante forty اربعين", 50: "cinquante fifty خمسين", 60: "soixante sixty ستين", 90: "quatre-vingt-dix ninety تسعين", 100: "cent hundred مائة مئة", 1000: "mille thousand الف",
}.items():
    for _w in _ws.split():
        _WORDS[normalize(_w)] = _val


def numbers_and_words(text: str) -> set[str]:
    out = {_canon(n) for n in numbers_in(text)}
    for t in tokens(text):
        if t in _WORDS:
            out.add(str(_WORDS[t]))
    return out


def _canon(n: str) -> str:
    return str(int(n)) if n.isdigit() else n


def _date_parts(d: date | str | None) -> set[str]:
    if not d:
        return set()
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d[:10])
        except ValueError:
            return set()
    return {str(d.year), str(d.month), str(d.day)}


@dataclass
class Failure:
    check: str
    reason: str
    claim_index: int | None = None


@dataclass
class ClaimResult:
    index: int
    claim: dict[str, Any]
    passed: bool = True
    failures: list[Failure] = field(default_factory=list)
    cited_chunks: list[str] = field(default_factory=list)
    cited_calcs: list[str] = field(default_factory=list)


@dataclass
class VerificationReport:
    claims: list[ClaimResult]
    global_failures: list[Failure] = field(default_factory=list)
    unanswered: list[int] = field(default_factory=list)
    check_counts: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def passed_claims(self) -> list[ClaimResult]:
        return [c for c in self.claims if c.passed]

    @property
    def all_ok(self) -> bool:
        return bool(self.claims) and all(c.passed for c in self.claims) and not self.global_failures

    def failure_reasons(self) -> list[str]:
        out = [f"claim {c.index}: [{f.check}] {f.reason}" for c in self.claims for f in c.failures]
        out += [f"[{f.check}] {f.reason}" for f in self.global_failures]
        return out

    def summary(self) -> dict[str, Any]:
        return {
            "checks": self.check_counts,
            "claims_total": len(self.claims),
            "claims_passed": len(self.passed_claims),
            "failures": self.failure_reasons(),
            "unanswered_sub_questions": self.unanswered,
        }


@dataclass
class VerifyContext:
    passages: dict[str, Candidate]  # "C12" -> candidate
    calcs: dict[str, CalcResult]  # "K1" -> result
    known_placeholders: set[str]
    as_of: date
    sub_questions: list[str]
    question_numbers: set[str]
    checker: ClaimChecker
    case_id: str | None = None
    names: N.NameData = field(default_factory=N.load_names)
    headers: dict[str, str] = field(default_factory=dict)
    question: str = ""  # the (pseudonymised) question: the facts an application claim relates the law to
    unmasked_question: str = ""  # masking switched off: names the user wrote himself are not "invented"  # "C12" -> title of the text, BO number and date: facts about the passage, not in its body


def _count(rep: VerificationReport, check: str, ok: bool) -> None:
    d = rep.check_counts.setdefault(check, {"passed": 0, "failed": 0})
    d["passed" if ok else "failed"] += 1


def verify_answer(answer: dict[str, Any], ctx: VerifyContext) -> VerificationReport:
    rep = VerificationReport([])
    claims = answer.get("claims") or []
    for idx, c in enumerate(claims):
        cr = ClaimResult(idx, c)
        rep.claims.append(cr)
        text = (c.get("text") or "").strip()
        support = c.get("support") or []

        def fail(check: str, reason: str) -> None:
            cr.passed = False
            cr.failures.append(Failure(check, reason, idx))
            _count(rep, check, False)

        # 1+2. citation exists, quote matches ------------------------------------------------------------------
        ok_cite = True
        if not text:
            fail("citation_exists", "empty claim text")
            continue
        if not support:
            if c.get("type") == "caveat" and not re.search(r"\d", text):
                _count(rep, "citation_exists", True)  # a number-free caveat may stand without a quote
            else:
                fail("citation_exists", "claim has no supporting citation")
                ok_cite = False
        for s in support:
            cid, kid, quote = s.get("chunk_id"), s.get("calc_id"), s.get("quote") or ""
            if bool(cid) == bool(kid):
                fail("citation_exists", "each support item needs exactly one of chunk_id / calc_id")
                ok_cite = False
                continue
            if cid:
                if cid not in ctx.passages:
                    fail("citation_exists", f"chunk id '{cid}' is not in the retrieved set")
                    ok_cite = False
                    continue
                cr.cited_chunks.append(cid)
                hay = ctx.headers.get(cid, "") + "\n" + ctx.passages[cid].chunk.body  # the date / number of the text may be quoted from its title
            else:
                if kid not in ctx.calcs:
                    fail("citation_exists", f"calculator output '{kid}' does not exist")
                    ok_cite = False
                    continue
                cr.cited_calcs.append(kid)
                hay = ctx.calcs[kid].text()
            if len(normalize(quote)) < 4 or not quote_in(quote, hay):
                fail("quote_matches", f"quote is not a substring of {cid or kid}")
        if ok_cite:
            _count(rep, "citation_exists", True)
        if cr.failures:
            continue

        # 3. placeholders intact ------------------------------------------------------------------------------------------
        bad = [p for p in find_placeholders(text) if p not in ctx.known_placeholders]
        masked = re.sub(r"\[[A-Z]+_\d+\]", " ", text)
        # a name or number printed in a cited PUBLIC passage (an appointed judge, a minister signing a decree) is not invented: only names /
        # identifiers absent from every cited passage count (the check exists to stop the model guessing who a placeholder is)
        public = normalize(" ".join(ctx.headers.get(c, "") + " " + ctx.passages[c].chunk.body for c in cr.cited_chunks if c in ctx.passages) + " " + ctx.unmasked_question)
        public_words = set(re.findall(r"\w+", public))

        def _invented(sp) -> bool:  # word by word: the detector may stretch a name over the next words ("خالد هرماش لرئاسة")
            frag = normalize(masked[sp.start:sp.end]).strip()
            if not frag or frag in public:
                return False
            if sp.kind != "PERSON":
                return True
            return any(w not in public_words for w in re.findall(r"\w+", frag)[:2])  # the name itself: first and family name
        ids = [sp.kind for sp in detect_patterns(masked) if sp.kind in DIRECT_IDENTIFIER_KINDS and _invented(sp)]
        nm = [sp for sp in N.detect_names(masked, ctx.names)[0] if _invented(sp)]
        if bad:
            fail("placeholders_intact", f"unknown placeholder(s) {bad}")
        elif ids or nm:
            fail("placeholders_intact", "a new name or identifier appears in the claim")
        else:
            _count(rep, "placeholders_intact", True)

        # 4. version is right -----------------------------------------------------------------------------------------------------
        vok = True
        for cid in cr.cited_chunks:
            cand = ctx.passages[cid]
            ch = cand.chunk
            if ch.verification_status not in TRUSTED_STATUSES:
                fail("version_is_right", f"{cid} is not at a trusted verification level")
                vok = False
            elif cand.source != "prior_version":
                vf = date.fromisoformat(ch.valid_from)
                vt = date.fromisoformat(ch.valid_to) if ch.valid_to else None
                if not (vf <= ctx.as_of and (vt is None or vt > ctx.as_of)):
                    fail("version_is_right", f"{cid} is not valid on {ctx.as_of.isoformat()} (valid {ch.valid_from} to {ch.valid_to or 'now'})")
                    vok = False
        if vok:
            _count(rep, "version_is_right", True)

        # 5. no stray numbers ------------------------------------------------------------------------------------------------------
        allowed: set[str] = set()
        for cid in cr.cited_chunks:
            allowed |= numbers_and_words(ctx.passages[cid].chunk.body) | numbers_and_words(ctx.headers.get(cid, ""))
            allowed |= _date_parts(ctx.passages[cid].chunk.valid_from) | _date_parts(ctx.passages[cid].chunk.valid_to)
        for kid in cr.cited_calcs:
            allowed |= numbers_and_words(ctx.calcs[kid].text())
        allowed |= _date_parts(ctx.as_of)
        if c.get("type") == "application":
            allowed |= {_canon(n) for n in ctx.question_numbers}  # restating the user's own facts
        stray = sorted(n for n in (numbers_and_words(text) | set()) if n not in allowed and n not in {"0"})
        if stray:
            fail("no_stray_numbers", f"numbers {stray} do not appear in the cited passages or tool outputs")
        else:
            _count(rep, "no_stray_numbers", True)

    # 6. claim is supported (independent checker, one batch) ---------------------------------------------------------------------------
    pending = [c for c in rep.claims if c.passed and (c.cited_chunks or c.cited_calcs)]
    if pending:
        items = []
        for c in pending:
            ctxt = " ".join(ctx.headers.get(i, "") + "\n" + ctx.passages[i].chunk.body for i in c.cited_chunks) + " " + " ".join(ctx.calcs[k].text() for k in c.cited_calcs)
            kind = c.claim.get("type") if c.claim.get("type") in ("rule", "application", "caveat") else "rule"
            items.append(ClaimItem(c.index, c.claim["text"], [s.get("quote", "") for s in c.claim.get("support", [])], ctxt, kind, ctx.question if kind == "application" else ""))
        for v in ctx.checker.check(items, ctx.case_id):
            cr = rep.claims[v.claim_id]
            if v.supported:
                _count(rep, "claim_is_supported", True)
            else:
                cr.passed = False
                cr.failures.append(Failure("claim_is_supported", v.reason or "claim not supported by its quote", v.claim_id))
                _count(rep, "claim_is_supported", False)

    # 7. sub-questions answered ----------------------------------------------------------------------------------------------------------------
    if ctx.sub_questions:
        ok_claims = rep.passed_claims
        answered: set[int] = set()
        any_tags = any(c.claim.get("answers") for c in ok_claims)
        for c in ok_claims:
            answered |= {a for a in (c.claim.get("answers") or []) if isinstance(a, int)}
        if not any_tags:
            blob = set(tokens(" ".join(c.claim.get("text", "") for c in ok_claims)))
            for i, q in enumerate(ctx.sub_questions):
                qt = {t for t in tokens(q) if len(t) > 3}
                if qt and len(qt & blob) / len(qt) >= 0.3:
                    answered.add(i)
        rep.unanswered = [i for i in range(len(ctx.sub_questions)) if i not in answered]
        for _ in ctx.sub_questions:
            pass
        _count(rep, "all_sub_questions_answered", not rep.unanswered)

    # 8. conflicts are shown -------------------------------------------------------------------------------------------------------------------------
    by_prov: dict[str, set[int]] = {}
    for cand in ctx.passages.values():
        if cand.source in ("search", "exact", "prior_version"):
            by_prov.setdefault(cand.chunk.provision_id, set()).add(cand.chunk.pv_id)
    cited_pv = {ctx.passages[i].chunk.pv_id for c in rep.passed_claims for i in c.cited_chunks}
    for pid, pvs in by_prov.items():
        if len(pvs) > 1 and not pvs <= cited_pv:
            rep.global_failures.append(Failure("conflicts_are_shown", f"two versions of {pid} were retrieved; state both with their dates"))
            _count(rep, "conflicts_are_shown", False)
        elif len(pvs) > 1:
            _count(rep, "conflicts_are_shown", True)
    return rep
