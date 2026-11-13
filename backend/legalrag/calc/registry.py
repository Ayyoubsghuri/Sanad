from __future__ import annotations

from typing import Any

from ..store.lawpack import LawPack
from .base import CalcError, CalcResult
from .basis import calc_articles
from .tools import EXAMPLES, TOOLS


def _match(result: dict, expect: dict) -> bool:
    for k, v in expect.items():
        got = result.get(k)
        if isinstance(v, float):
            if got is None or abs(float(got) - v) > 0.005:
                return False
        elif got != v:
            return False
    return True


def run_examples(pack: LawPack) -> dict[str, dict[str, Any]]:
    """Run every worked example against the pack. Returns per-tool {passed, total, official, verified}."""
    out: dict[str, dict[str, Any]] = {}
    for name, (fn, model, _desc) in TOOLS.items():
        exs = EXAMPLES.get(name, [])
        passed = 0
        for ex in exs:
            try:
                r = fn(pack, model(**ex["inputs"]))
                passed += int(_match(r.result, ex["expect"]))
            except CalcError:
                pass
        official = bool(exs) and all(e["official"] for e in exs)
        out[name] = {"passed": passed, "total": len(exs), "official_examples": official, "verified": bool(exs) and official and passed == len(exs)}
    return out


class CalculatorService:
    def __init__(self, pack: LawPack):
        self.pack = pack
        self.status = run_examples(pack)

    def describe(self) -> list[dict]:
        return [
            {"tool": n, "description": d, "input_schema": m.model_json_schema(), "verification": "verified_against_official_examples" if self.status[n]["verified"] else "unverified",
             "examples": self.status[n]}
            for n, (_f, m, d) in TOOLS.items()
        ]

    def run(self, tool: str, inputs: dict) -> CalcResult:
        if tool not in TOOLS:
            raise CalcError("abstain", f"unknown calculator '{tool}'")
        fn, model, _ = TOOLS[tool]
        try:
            parsed = model(**inputs)
        except Exception as e:  # pydantic ValidationError -> ask for input
            missing = [".".join(map(str, err["loc"])) for err in getattr(e, "errors", lambda: [])()]
            raise CalcError("needs_input", f"invalid inputs: {e.__class__.__name__}", missing) from e
        res = fn(self.pack, parsed)
        res.verified = self.status[tool]["verified"]
        try:
            from datetime import date as _d

            on = _d.fromisoformat(res.as_of) if res.as_of else _d.today()
            pids = [r.get("provision_id") for r in res.table_rows if isinstance(r, dict) and r.get("provision_id")]
            res.articles = calc_articles(self.pack, tool, on, {"_provisions": pids})
            if res.articles:
                res.legal_basis = list(dict.fromkeys([*(f"{a.get('law_short') or a['law'] or a['instrument_id']}, art. {a['number']}" for a in res.articles), *res.legal_basis]))
        except Exception:  # noqa: BLE001 - quoting the law is an addition: a calculation is never lost because of it
            res.articles = []
        return res
