"""Large retrieval benchmark made from YOUR pack, NO language model and no cost: for each sampled article two search-box style queries are cut
from the article itself, then Sanad's search has to bring that article back.  The gold answer is the article the query came from, so it is
correct by construction (unlike the labels of public sets).

    py tools\\synthbench.py --n 1000                 1000 articles, two queries each (a few minutes)
    py tools\\synthbench.py --n 200                  a quick test
    py tools\\synthbench.py --codes labor,penal      only these codes (moudawana, labor, traffic, commercial, penal, obligations, procedure)
    py tools\\synthbench.py --llm                    OPTIONAL: a model writes real-life questions in Darija and formal Arabic instead (saved after the
                                                      first run; --run-only then reuses them for free)

The two queries:  "clause" = the article's first sentence with a quarter of its words dropped;  "keywords" = 5 words of the article, as typed in a
search box.  They are NOT how a citizen asks, and they share words with the article, so the scores are higher than for real users: use them to
compare versions of Sanad with each other (before/after a change) and to catch breakages, not as an absolute claim.  Darija cannot be tested
without a model: the 36 real Darija questions of tools\\moroccoregqa.py are the Darija check.

Stop the backend first.  Report: reports\\synthbench_<date>.json/.csv + the summary on screen.

How to read it: a question written FROM an article tends to reuse its words, so these scores are higher than for real users; the model is told
to avoid the article's phrases and to write Darija and formal Arabic separately, which makes it harder.  Use the numbers to compare versions
of Sanad with each other (before/after a change), and the Darija/Arabic gap, not as an absolute claim."""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
REPORTS = ROOT / "reports"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CODES = {
    "moudawana": "LAW_70.03", "labor": "LAW_65.99", "traffic": "LAW_52.05", "commercial": "LAW_15.95", "penal": "DAHIR_1.59.413",
    "obligations": "DAHIR_DOC-1913", "procedure": "LAW_22.01",
}
DEFAULT_CODES = ("moudawana", "labor", "traffic", "commercial", "penal")
KS = (1, 3, 5, 10)
MIN_CHARS, MAX_CHARS = 90, 1100
SKIP = re.compile(r"^\s*(?:\(?\s*(?:نسخت|ألغيت|الغيت|نسخ)|.{0,40}(?:تم نسخ|ملغاة|منسوخة))")

SYSTEM = (
    "You write test questions for a Moroccan law search engine. For each article you are given, write the question an ordinary person would ask "
    "whose answer is found in THAT article. Rules: (1) two versions: `darija` = natural spoken Moroccan Darija in Arabic script; `msa` = the same "
    "question in clear formal Arabic. (2) Never mention an article number, a law name or the word 'article/مادة/فصل'. (3) Do not copy phrases of 3 or "
    "more words from the article: use everyday words, as someone who has never read the law. (4) One short question each, about the situation, not "
    "about the text. (5) If the article is only a definition, list of cross-references or has no rule a person could ask about, return empty strings."
)
SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
    "id": {"type": "string"}, "darija": {"type": "string"}, "msa": {"type": "string"}}, "required": ["id", "darija", "msa"]}}}, "required": ["items"]}


def article_text(pack, iid: str, num: str, on: date) -> str | None:
    m = re.match(r"(\d+)(-\d+)?$", num)
    if not m:
        return None
    pid = pack.find_provision(iid, int(m.group(1)), m.group(2) or "")
    v = pid and pack.version_at(pid, on)
    if not v:
        return None
    t = pack.texts(v["pv_id"])
    return (t.get("ar") or next(iter(t.values()), {"text": ""}))["text"]


def sample_articles(pack, codes: dict[str, str], per_code: int, seed: int, on: date) -> list[dict]:
    """Up to `per_code` usable articles of each code (every edition of the law counted once per number), a fixed random sample per seed."""
    from legalrag.services import tools as T

    rng = random.Random(seed)
    out: list[dict] = []
    for code, iid in codes.items():
        if iid not in pack.instrument_ids():
            print(f"  {code}: {iid} is not in your pack - skipped")
            continue
        seen: dict[str, tuple[str, str]] = {}
        for ed in reversed(T.family(pack, iid)):  # newest edition first
            for p in pack.provisions_of(ed):
                num = str(p["number"])
                if num in seen or not re.fullmatch(r"\d+(?:-\d+)?", num):
                    continue
                t = article_text(pack, ed, num, on)
                if t and MIN_CHARS <= len(t.strip()) and not SKIP.search(t.strip()):
                    seen[num] = (ed, t.strip())
        nums = sorted(seen)
        rng.shuffle(nums)
        for num in nums[:per_code]:
            ed, t = seen[num]
            out.append({"id": f"{code}:{num}", "code": code, "number": num, "instrument": ed, "text": t[:MAX_CHARS]})
        print(f"  {code}: {len(nums)} usable articles, {min(len(nums), per_code)} sampled")
    return out


_NOTE = re.compile(r"^\s*\((?:[^()]*?(?:بموجب|غيرت|تممت|نسخت|عوضت|غير ت|الظهير الشريف|ج\.ر)[^()]*?)\)\s*")


def extractive_queries(text: str, rng: random.Random) -> dict[str, str]:
    """{"clause": ..., "keywords": ...} cut from the article text (no model)."""
    from legalrag.text import stopwords
    from legalrag.text.arabic import tokens

    t = _NOTE.sub("", text.strip())
    t = re.sub(r"\s+", " ", t)
    sents = [x.strip() for x in re.split(r"[.؛:]| - ", t) if len(tokens(x)) >= 6]
    first = (sents[0] if sents else t)
    words = [w for w in re.findall(r"[\u0621-\u064A]+", first)][:18]
    keep = [w for i, w in enumerate(words) if i == 0 or rng.random() > 0.25]
    content = [w for w in re.findall(r"[\u0621-\u064A]+", t[:600]) if len(w) > 3 and w not in stopwords.ALL]
    content = list(dict.fromkeys(content))
    rng.shuffle(content)
    return {"clause": " ".join(keep), "keywords": " ".join(content[:5])}


def generate(llm, items: list[dict], cache: Path, batch: int = 8) -> dict[str, dict]:
    from legalrag.llm.providers import GenRequest

    done: dict[str, dict] = {}
    if cache.exists():
        for l in cache.read_text("utf-8").splitlines():
            if l.strip():
                r = json.loads(l)
                done[r["id"]] = r
    todo = [i for i in items if i["id"] not in done]
    print(f"questions: {len(done)} saved, {len(todo)} to write")
    cache.parent.mkdir(exist_ok=True)
    with open(cache, "a", encoding="utf-8") as f:
        for k in range(0, len(todo), batch):
            chunk = todo[k:k + batch]
            try:
                got = llm.generate_json(GenRequest(SYSTEM, {"articles": [{"id": c["id"], "text": c["text"]} for c in chunk]}, SCHEMA, [], None, kind="synthbench"))
            except Exception as e:  # noqa: BLE001 - one failed batch must not stop the run
                print(f"  batch {k // batch + 1} failed: {str(e)[:150]}")
                continue
            ids = {c["id"] for c in chunk}
            for it in got.get("items") or []:
                if it.get("id") in ids:
                    rec = {"id": it["id"], "darija": (it.get("darija") or "").strip(), "msa": (it.get("msa") or "").strip()}
                    done[rec["id"]] = rec
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            print(f"  {min(k + batch, len(todo))}/{len(todo)}")
    return done


def calibration(runs: list[tuple[float, int | None]], title: str) -> None:
    """runs = [(top reranker score, rank of the best gold article or None)].  Where should Sanad stop answering ("no answer")?
    answered = top score >= t.  A run is GOOD when the gold article is in the top 3."""
    if not runs:
        return
    print(f"\nWhere to set the 'no answer' threshold - {title} ({len(runs)} runs)")
    print("  threshold   answers   of these, article in top 3   questions lost by refusing (article was in top 3)")
    for t in (0.02, 0.05, 0.10, 0.15, 0.20, 0.30):
        ans = [r for r in runs if r[0] >= t]
        good = sum(1 for _, rk in ans if rk and rk <= 3)
        lost = sum(1 for sc, rk in runs if sc < t and rk and rk <= 3)
        print(f"  {t:8.2f}   {len(ans) / len(runs):7.0%}   {good / max(len(ans), 1):26.0%}   {lost / len(runs):.0%}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000, help="total questions (shared equally between the codes)")
    ap.add_argument("--codes", default=",".join(DEFAULT_CODES))
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--llm", action="store_true", help="use a language model to write real-life questions (Darija + formal Arabic); default: no model")
    ap.add_argument("--run-only", action="store_true", help="with --llm: do not call the model, use the saved questions")
    ap.add_argument("--date")
    a = ap.parse_args()

    from legalrag.config import Settings
    from legalrag.pipeline import understand as U
    from legalrag.retrieval.engine import RetrievalRequest
    from legalrag.services import tools as T
    from legalrag.state import build_context

    ctx = build_context(Settings())
    if not ctx.pack_usable():
        print("no usable law pack:", ctx.pack_error)
        return 2
    pack = ctx.pack
    on = date.fromisoformat(a.date) if a.date else ctx.today_fn()
    codes = {c: CODES[c] for c in a.codes.split(",") if c in CODES}
    per_code = max(1, a.n // max(1, len(codes)))

    items = sample_articles(pack, codes, per_code, a.seed, on)
    cache = REPORTS / "synth_questions.jsonl"
    langs = ("msa", "darija") if a.llm else ("clause", "keywords")
    names = {"msa": "formal Arabic", "darija": "Darija", "clause": "first sentence (words dropped)", "keywords": "5 keywords"}
    if not a.llm:
        rng = random.Random(a.seed)
        qs = {i["id"]: {"id": i["id"], **extractive_queries(i["text"], rng)} for i in items}
    elif a.run_only:
        saved = {}
        if cache.exists():
            for l in cache.read_text("utf-8").splitlines():
                if l.strip():
                    r = json.loads(l)
                    saved[r["id"]] = r
        qs = saved
    else:
        llm = ctx.llm()
        if llm is None:
            print("no language model configured (needed once to write the questions); use --run-only if questions are already saved")
            return 2
        qs = generate(llm, items, cache)
    fam = {c: set(T.family(pack, iid)) for c, iid in codes.items()}
    rows = []
    wanted = {i["id"]: i for i in items}
    todo = [(wanted[k], q) for k, q in qs.items() if k in wanted and any(q.get(l) for l in langs)]
    print(f"\nrunning the search on {len(todo)} questions ...")
    for n, (it, q) in enumerate(todo, start=1):
        gold = (it["code"], it["number"])
        row = {"id": it["id"], "code": it["code"], "ranks": {}, "top3": {}}
        for lang in langs:
            text = q.get(lang)
            if not text:
                continue
            try:
                u = U.understand(text, pack, today=ctx.today_fn(), explicit_as_of=on, max_sub=ctx.settings.max_subquestions)
                ret = ctx.engine.retrieve(RetrievalRequest(query=text, as_of=on, sub_questions=u.sub_questions, domains=u.domains, exact_refs=u.exact_refs,
                                                           focus_instruments=u.focus_instruments, today=ctx.today_fn(), lang="ar", keep=12))
                seen, ranked = set(), []
                for c in sorted(ret.candidates, key=lambda c: -c.score):
                    code = next((k for k, f in fam.items() if c.chunk.instrument_id in f), None)
                    if (code, c.chunk.number) not in seen:
                        seen.add((code, c.chunk.number))
                        ranked.append((code, c.chunk.number))
                row["ranks"][lang] = next((i + 1 for i, k in enumerate(ranked) if k == gold), None)
                row.setdefault("top_score", {})[lang] = round(max((c.score for c in ret.candidates), default=0.0), 4)
                row["top3"][lang] = [f"{c}:{nm}" for c, nm in ranked[:3]]
                row.setdefault("q", {})[lang] = text
            except Exception as e:  # noqa: BLE001
                row["ranks"][lang] = None
                row["top3"][lang] = [f"error: {str(e)[:80]}"]
        rows.append(row)
        if n % 50 == 0:
            print(f"  {n}/{len(todo)}")

    def rate(rs, lang, k):
        v = [r["ranks"].get(lang) for r in rs if lang in r["ranks"]]
        return (sum(1 for x in v if x and x <= k) / len(v), len(v)) if v else (0.0, 0)

    print(f"\n{len(rows)} questions (gold = the article each question was written from)")
    for lang in langs:
        print(f"\n{names[lang]:32}" + "   ".join(f"hit@{k}={rate(rows, lang, k)[0]:.0%}" for k in KS) + f"   (n={rate(rows, lang, 1)[1]})")
    print("\nhit@5 by code:           " + "   ".join(f"{l:>9}" for l in langs))
    for c in sorted({r["code"] for r in rows}):
        rs = [r for r in rows if r["code"] == c]
        print(f"  {c:12} n={len(rs):4}   " + "   ".join(f"{rate(rs, l, 5)[0]:>9.0%}" for l in langs))
    for lang in langs:
        calibration([(r.get("top_score", {}).get(lang, 0.0), r["ranks"].get(lang)) for r in rows if lang in r["ranks"]], names[lang])
    first_lang = langs[0]
    miss = [r for r in rows if r["ranks"].get(first_lang) is None or r["ranks"][first_lang] > 10]
    print(f"\n'{first_lang}' queries whose article is not in the top 10: {len(miss)}  (listed in the .json)")

    REPORTS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    (REPORTS / f"synthbench_{stamp}.json").write_text(json.dumps({"date": str(on), "n": len(rows), "rows": rows, "misses": [r["id"] for r in miss], "queries": list(langs)}, ensure_ascii=False, indent=1), "utf-8")
    with open(REPORTS / f"synthbench_{stamp}.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "code", "lang", "question", "rank_of_gold", "top3"])
        for r in rows:
            for lang, rk in r["ranks"].items():
                w.writerow([r["id"], r["code"], lang, (r.get("q") or {}).get(lang, ""), rk, " ".join(r["top3"].get(lang, []))])
    print(f"\nreport: reports\\synthbench_{stamp}.json / .csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
