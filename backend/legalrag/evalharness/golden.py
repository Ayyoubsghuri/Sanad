"""Golden-set evaluation generated from the pack itself (no lawyer needed to write the questions) and scored with
deterministic checks, never an LLM judge. Gates are the blueprint's PROPOSED starting values; tune them as the set grows.

It tests retrieval, version choice, quoting, abstention, calculators, pseudonymisation and fallback behaviour.
It does NOT test legal judgement, and says so in its report."""
from __future__ import annotations

import random
import re
import tempfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from ..calc.registry import run_examples
from ..llm.providers import GenRequest, ScriptedProvider
from ..privacy.gateway import CloudUnavailable
from ..retrieval.engine import RetrievalRequest
from ..schemas import PrepareRequest, RunRequest
from ..state import AppContext
from ..text.arabic import numbers_in

GATES = {  # metric -> (comparison, threshold)
    "recall_at_10": (">=", 0.95), "version_correctness": (">=", 0.99), "citation_validity": (">=", 1.0), "claim_support_unsupported_rate": ("<=", 0.02),
    "wrong_answer_rate": ("<=", 0.03), "correct_abstention": (">=", 0.95), "over_abstention": ("<=", 0.10), "false_premise_rejection": (">=", 0.90),
    "calculator_cases": (">=", 1.0), "pseudo_recall_direct_identifiers": (">=", 0.99), "fallback_behaviour": (">=", 1.0),
}


@dataclass
class Metric:
    name: str
    passed: int = 0
    total: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def value(self) -> float | None:
        return (self.passed / self.total) if self.total else None


def _gate(name: str, value: float | None) -> bool | None:
    if value is None:
        return None
    op, th = GATES[name]
    return value >= th if op == ">=" else value <= th


def _oracle(passages_by_req: Callable[[GenRequest], list[dict]]):
    """A faithful scripted 'model': cites the first passage with a verbatim quote. Exercises the verification path end to end."""
    def script(req: GenRequest) -> dict[str, Any]:
        ps = req.payload.get("passages", [])
        if not ps:
            return {"assumptions": [], "claims": [], "abstain_reason": "no passages"}
        p = ps[0]
        quote = " ".join(p["text"].split()[:8])
        return {"assumptions": [], "claims": [{"type": "rule", "text": " ".join(p["text"].split()[:12]), "answers": [0], "support": [{"chunk_id": p["chunk_id"], "quote": quote}]}]}
    return script


def _hostile(req: GenRequest) -> dict[str, Any]:
    """A bad model: invented chunk id, wrong quote, stray number. Nothing of it may ship."""
    return {"assumptions": [], "claims": [
        {"type": "rule", "text": "The deadline is 999 days.", "support": [{"chunk_id": "C999999", "quote": "invented quote"}]},
        {"type": "rule", "text": "Another invented rule with 777.", "support": [{"chunk_id": req.payload["passages"][0]["chunk_id"] if req.payload.get("passages") else "C1", "quote": "this quote is not in the passage"}]},
    ]}


def run_golden(ctx: AppContext, seed: int = 7) -> dict[str, Any]:
    pack = ctx.pack
    rnd = random.Random(seed)
    m = {k: Metric(k) for k in GATES}
    today = ctx.today_fn()
    saved_override, saved_mode = ctx.llm_override, ctx.db.get_settings().get("mode")
    case = ctx.db.create_case(label="eval")
    detail: dict[str, Any] = {"generated": {}}

    provs = [p for i in pack.instruments() for p in pack.provisions_of(i["instrument_id"])]
    cur = []
    for p in provs:
        v = pack.version_at(p["provision_id"], today)
        if v:
            cur.append((p, v))

    # --- retrieval recall: first words of the article itself as the question (offline, no model) -----------------------------
    for p, v in cur:
        body = (pack.texts(v["pv_id"]).get(v["controlling_lang"]) or next(iter(pack.texts(v["pv_id"]).values())))["text"]
        q = " ".join(body.split()[:10])
        res = ctx.engine.retrieve(RetrievalRequest(query=q, as_of=today, today=today, expand=False, keep=10))
        ok = any(c.chunk.provision_id == p["provision_id"] for c in res.candidates)
        m["recall_at_10"].total += 1
        m["recall_at_10"].passed += int(ok)
        if not ok:
            m["recall_at_10"].failures.append(p["provision_id"])
    detail["generated"]["article_lookups"] = len(cur)

    # --- version correctness: every provision with >= 2 versions, a date inside each range ---------------------------------------------
    for p in provs:
        vs = pack.versions(p["provision_id"])
        if len(vs) < 2:
            continue
        for v in vs:
            if v["verification_status"] not in ("verified", "single_source", "derived"):
                continue
            d = date.fromisoformat(v["valid_from"])
            body = (pack.texts(v["pv_id"]).get(v["controlling_lang"]) or next(iter(pack.texts(v["pv_id"]).values())))["text"]
            res = ctx.engine.retrieve(RetrievalRequest(query=" ".join(body.split()[:10]), as_of=d, today=today, expand=False, keep=10))
            hits = [c for c in res.candidates if c.chunk.provision_id == p["provision_id"]]
            ok = bool(hits) and all(c.chunk.pv_id == v["pv_id"] for c in hits)
            m["version_correctness"].total += 1
            m["version_correctness"].passed += int(ok)
            if not ok:
                m["version_correctness"].failures.append(f"{p['provision_id']}@{d}")

    # --- false premises: alter a number in a real article -------------------------------------------------------------------------------------
    from ..pipeline.understand import check_premises, understand

    aliases_rev = {}
    for a, iid in pack.aliases().items():
        aliases_rev.setdefault(iid, a)
    for p, v in cur:
        text = next(iter(pack.texts(v["pv_id"]).values()))["text"]
        nums = [n for n in numbers_in(text) if n.isdigit()]
        alias = aliases_rev.get(p["instrument_id"])
        if not nums or not alias or p["number_int"] is None:
            continue
        wrong = str(int(nums[0]) + 7)
        q = f"Article {p['number_int']} {alias} says {wrong} days. Is that right?"
        u = understand(q, pack, today=today, explicit_as_of=today)
        ok = bool(check_premises(q, u, pack))
        m["false_premise_rejection"].total += 1
        m["false_premise_rejection"].passed += int(ok)
        if not ok:
            m["false_premise_rejection"].failures.append(p["provision_id"])

    # --- abstention: unanswerable / foreign-law questions must not produce a model answer ---------------------------------------------------------
    ctx.llm_override = ScriptedProvider(_oracle(lambda r: []))
    ctx.db.set_settings({"mode": "hybrid", "auto_approve_send": True})
    from ..pipeline.orchestrator import QueryPipeline

    pipe = QueryPipeline(ctx)
    unanswerable = ["zxqv blorptastic quibble frumious", "What is the speed of light in a vacuum on Mars?", "كيف أصنع كعكة الشوكولاتة بالفراولة"]
    for q in unanswerable:
        out = pipe.run(pipe.prepare(PrepareRequest(question=q, case_id=case))["query_id"], RunRequest())
        ok = out["status"] in ("abstained", "needs_clarification")
        m["correct_abstention"].total += 1
        m["correct_abstention"].passed += int(ok)
        if not ok:
            m["correct_abstention"].failures.append(q)
    for p, v in cur[:20]:
        body = (pack.texts(v["pv_id"]).get("ar") or next(iter(pack.texts(v["pv_id"]).values())))["text"]
        out = pipe.run(pipe.prepare(PrepareRequest(question=" ".join(body.split()[:10]), case_id=case, as_of=today))["query_id"], RunRequest())
        m["over_abstention"].total += 1
        m["over_abstention"].passed += int(out["status"] == "abstained")  # passed == abstained; gate is an upper bound
        if out["status"] == "abstained":
            m["over_abstention"].failures.append(p["provision_id"])
        # --- citation validity + wrong answers with the faithful oracle ------------------------------------------------------------------------------
        if out["status"] in ("answered", "partial"):
            ids = {s["id"] for s in out["sources"] + out["related"]}
            bad = [c for c in out["claims"] for sid in c["sources"] if sid not in ids]
            m["citation_validity"].total += 1
            m["citation_validity"].passed += int(not bad)
            m["wrong_answer_rate"].total += 1
            wrong = any(c.get("verified") is not True for c in out["claims"])
            m["wrong_answer_rate"].passed += int(wrong)  # passed == wrong; the gate is an upper bound
            if wrong:
                m["wrong_answer_rate"].failures.append(p["provision_id"])

    # hostile model: invalid citations must never be shipped (0 invalid citations reach the user)
    ctx.llm_override = ScriptedProvider(_hostile)
    for p, v in cur[:10]:
        body = next(iter(pack.texts(v["pv_id"]).values()))["text"]
        out = pipe.run(pipe.prepare(PrepareRequest(question=" ".join(body.split()[:10]), case_id=case, as_of=today))["query_id"], RunRequest())
        m["citation_validity"].total += 1
        m["citation_validity"].passed += int(not out.get("claims"))
        if out.get("claims"):
            m["citation_validity"].failures.append(f"hostile claim shipped for {p['provision_id']}")

    # --- fallback: cloud outage and offline mode must end in quoted passages or an abstention ------------------------------------------------------------------
    def boom(_: GenRequest):
        raise CloudUnavailable("simulated outage")

    ctx.llm_override = ScriptedProvider(boom)
    for p, v in cur[:5]:
        body = next(iter(pack.texts(v["pv_id"]).values()))["text"]
        out = pipe.run(pipe.prepare(PrepareRequest(question=" ".join(body.split()[:10]), case_id=case, as_of=today))["query_id"], RunRequest())
        m["fallback_behaviour"].total += 1
        m["fallback_behaviour"].passed += int(out["status"] in ("extractive_only", "abstained") and not out.get("claims"))
    ctx.db.set_settings({"mode": "offline"})
    for p, v in cur[:5]:
        body = next(iter(pack.texts(v["pv_id"]).values()))["text"]
        out = pipe.run(pipe.prepare(PrepareRequest(question=" ".join(body.split()[:10]), case_id=case, as_of=today))["query_id"], RunRequest())
        m["fallback_behaviour"].total += 1
        m["fallback_behaviour"].passed += int(out["status"] in ("extractive_only", "abstained") and not ctx.db.query("SELECT 1 FROM outbound_log WHERE kind='generate' AND status='ok' LIMIT 1"))

    # --- calculators: worked examples ------------------------------------------------------------------------------------------------------------------------------------
    for tool, st_ in run_examples(pack).items():
        m["calculator_cases"].total += st_["total"]
        m["calculator_cases"].passed += st_["passed"]

    # --- pseudonymisation recall on SYNTHETIC identifiers (never real data) ---------------------------------------------------------------------------------------------
    for text, planted in synthetic_pseudonymisation_cases(rnd, 60):
        r = ctx.pseudo.pseudonymise(text, ctx.db.create_case(label="eval-synthetic"))
        for kind, value in planted:
            if kind in ("CIN", "PHONE", "EMAIL", "RIB"):
                m["pseudo_recall_direct_identifiers"].total += 1
                ok = re.sub(r"\s+", "", value) not in re.sub(r"\s+", "", r.text)
                m["pseudo_recall_direct_identifiers"].passed += int(ok)
                if not ok:
                    m["pseudo_recall_direct_identifiers"].failures.append(f"{kind}")
            else:  # names: reported, gate set after measurement
                detail.setdefault("name_recall", {"passed": 0, "total": 0})
                detail["name_recall"]["total"] += 1
                detail["name_recall"]["passed"] += int(value not in r.text)

    ctx.llm_override = saved_override
    ctx.db.set_settings({"mode": saved_mode})
    report = {}
    for k, met in m.items():
        val = met.value
        if k == "over_abstention" and met.total:
            val = met.passed / met.total
        report[k] = {"value": None if val is None else round(val, 4), "n": met.total, "gate": f"{GATES[k][0]} {GATES[k][1]}", "pass": _gate(k, val), "failures": met.failures[:10]}
    # claim support rate is estimated from the verifier's own counters on the oracle runs
    report["claim_support_unsupported_rate"] = {"value": None, "n": 0, "gate": "<= 0.02", "pass": None, "failures": [], "note": "needs the independent checker's counters over real-model runs"}
    ran = [v["pass"] for v in report.values() if v["pass"] is not None]
    return {"all_gates_pass": all(ran) if ran else None, "metrics": report, "detail": detail, "pack_version": pack.version,
            "scope": "Tests retrieval, version choice, quoting, abstention, calculators, pseudonymisation and fallback. It does not test legal judgement."}


def synthetic_pseudonymisation_cases(rnd: random.Random, n: int) -> list[tuple[str, list[tuple[str, str]]]]:
    firsts = ["Karim", "Salma", "Youssef", "Imane", "Rachid", "Nadia", "Hamza", "Khadija"]
    lasts = ["Benali", "Idrissi", "Tazi", "Alaoui", "Mansouri", "Lahlou"]
    out = []
    for _ in range(n):
        name = f"{rnd.choice(firsts)} {rnd.choice(lasts)}"
        cin = f"{rnd.choice('ABCDEFGHJK')}{rnd.choice('ABCDEFGHJK')}{rnd.randint(100000, 999999)}"
        phone = f"06{rnd.randint(10, 99)} {rnd.randint(10, 99)} {rnd.randint(10, 99)} {rnd.randint(10, 99)}"
        email = f"{name.split()[0].lower()}{rnd.randint(1, 99)}@example.org"
        rib = "".join(str(rnd.randint(0, 9)) for _ in range(24))
        text = f"M. {name} (CIN {cin}) joignable au {phone} ou {email}. RIB {rib}. Licencié le {rnd.randint(1, 28)}/0{rnd.randint(1, 9)}/2025."
        out.append((text, [("PERSON", name), ("CIN", cin), ("PHONE", phone), ("EMAIL", email), ("RIB", rib)]))
    return out
