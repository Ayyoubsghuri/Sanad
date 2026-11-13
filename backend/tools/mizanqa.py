"""Test Sanad on MizanQA (Moroccan legal multiple-choice questions, Bahaj et al. 2025) with a small sample per legal area.

    py tools\\mizanqa.py --list                      the areas in the dataset and how many questions each has
    py tools\\mizanqa.py                             10 questions from EVERY area (same questions each run: --seed 7)
    py tools\\mizanqa.py --per 5 --areas family criminal     5 from each area whose name contains "family" or "criminal"
    py tools\\mizanqa.py --baseline                  also ask the language model alone (no law pack) to see what retrieval adds
    py tools\\mizanqa.py --resume                    continue the last run (questions already answered are skipped)
    py tools\\mizanqa.py --file mizan.parquet        use a file you downloaded (json, jsonl, csv or parquet) instead of Hugging Face
    py tools\\mizanqa.py --coverage                  NO model, a few minutes: which laws the questions need and whether the pack has them
    py tools\\mizanqa.py --coverage --per 0          the same on ALL questions of the dataset
    py tools\\mizanqa.py --date 2026-08-01           answer with the law in force on that date (MizanQA predates the new civil
                                                    procedure law 58.25, in force from 2026-08-24)

The dataset (https://huggingface.co/datasets/adlbh/MizanQA-v0) is downloaded the first time with the `datasets` package
(`py -m pip install datasets`); it is cached after that.  Stop the backend while this runs (it loads the same models).

How a question is scored
  1. Sanad gets the question with its numbered options, exactly as a user would type it (masking off: exam text has no private data).
  2. The final choice is made by the language model from Sanad's verified answer AND the articles Sanad retrieved (the articles are the
     authority; where they are silent it may use its own knowledge, exactly as Sanad does for a user).  Nothing found = nothing selected.
  3. Scores, as in the MizanQA paper:  ACC = the selected set equals the correct set exactly;  F1 = per-question overlap;
     PARTIAL = (correct picked - wrong picked) / correct, floored at 0.
Report: reports\\mizanqa_<date>.json (every question, Sanad's answer, the articles it cited, the choice, the score) + .csv + a table
per area on screen.  Retrieval is reported too: how many answers cited at least one article, and how many abstained."""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
REPORTS = ROOT / "reports"
HF_ID = "adlbh/MizanQA-v0"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ------------------------------------------------------------------------------------------------ dataset
Q_KEYS = ("question", "Question", "query", "prompt", "text")
OPT_KEYS = ("options", "choices", "Options", "answers_options", "propositions")
ANS_KEYS = ("answer", "answers", "correct", "correct_answers", "label", "labels", "Answer", "gold")
CAT_KEYS = ("category", "Category", "domain", "subject", "law", "field", "topic", "source", "area")
LETTERS_LAT = "ABCDEFGHIJKLMNOP"
LETTERS_AR = "أبجدهوزحطيكلمنسع"


def _load_rows(file: str | None) -> list[dict]:
    if file:
        p = Path(file)
        if p.suffix == ".jsonl":
            return [json.loads(l) for l in p.read_text("utf-8").splitlines() if l.strip()]
        if p.suffix == ".json":
            d = json.loads(p.read_text("utf-8"))
            return d if isinstance(d, list) else next(v for v in d.values() if isinstance(v, list))
        if p.suffix == ".csv":
            return list(csv.DictReader(p.open(encoding="utf-8")))
        if p.suffix == ".parquet":
            import pandas as pd
            return pd.read_parquet(p).to_dict("records")
        sys.exit(f"unknown file type: {p.suffix}")
    try:
        from datasets import load_dataset
    except ImportError:
        sys.exit("install the datasets package first:  py -m pip install datasets   (or download the dataset and pass --file)")
    ds = load_dataset(HF_ID)
    rows: list[dict] = []
    for split in ds:
        rows += [dict(r, _split=split) for r in ds[split]]
    return rows


def _pick(row: dict, keys: tuple[str, ...]):
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return k, row[k]
    return None, None


def _options(raw) -> list[str]:
    if raw is None:
        return []
    if hasattr(raw, "tolist"):
        raw = raw.tolist()
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith(("[", "{")):
            try:
                return _options(json.loads(s))
            except json.JSONDecodeError:
                pass
        parts = [p.strip() for p in re.split(r"\n+", s) if p.strip()]
        return [re.sub(r"^\s*(?:[A-Pa-p]|[أبجدهوزحطيكلمنسع]|\d{1,2})\s*[).:\-]\s*", "", p) for p in parts]
    if isinstance(raw, dict):
        return [str(v) for _, v in sorted(raw.items(), key=lambda kv: str(kv[0]))]
    return [str(x) for x in raw]


def _answer_set(raw, options: list[str], zero_based: bool | None = None) -> set[int]:
    """-> 0-based indices of the correct options, whatever form the dataset uses (indices, letters, option texts, '1,3')."""
    if raw is None:
        return set()
    if hasattr(raw, "tolist"):
        raw = raw.tolist()
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith("["):
            try:
                return _answer_set(json.loads(s), options, zero_based)
            except json.JSONDecodeError:
                pass
        if s in options:
            return {options.index(s)}
        raw = [x for x in re.split(r"[,;،\s]+", s) if x]
    if isinstance(raw, (int, float)):
        raw = [raw]
    out: set[int] = set()
    items = list(raw)
    nums = [x for x in items if isinstance(x, (int, float)) or (isinstance(x, str) and x.isdigit())]
    if zero_based is None:
        zero_based = any(int(x) == 0 for x in nums)
    for x in items:
        if isinstance(x, (int, float)) or (isinstance(x, str) and x.isdigit()):
            i = int(x) - (0 if zero_based else 1)
        elif isinstance(x, str) and len(x) == 1 and x.upper() in LETTERS_LAT:
            i = LETTERS_LAT.index(x.upper())
        elif isinstance(x, str) and len(x) == 1 and x in LETTERS_AR:
            i = LETTERS_AR.index(x)
        elif isinstance(x, str) and x.strip() in options:
            i = options.index(x.strip())
        else:
            continue
        if 0 <= i < len(options):
            out.add(i)
    return out


def load(file: str | None) -> list[dict]:
    rows = _load_rows(file)
    if not rows:
        sys.exit("the dataset is empty")
    qk, _ = _pick(rows[0], Q_KEYS)
    ck, _ = _pick(rows[0], CAT_KEYS)
    if not qk:
        sys.exit(f"cannot find the question field; columns are: {list(rows[0])}")
    # numbers as answers: 0-based or 1-based is decided once for the whole dataset (a row "[1, 3]" alone cannot tell)
    zero, top = False, False
    for r in rows:
        _, o = _pick(r, OPT_KEYS)
        _, a = _pick(r, ANS_KEYS)
        a = a.tolist() if hasattr(a, "tolist") else a
        if isinstance(a, str) and a.strip().startswith("["):
            try:
                a = json.loads(a)
            except json.JSONDecodeError:
                pass
        vals = [a] if isinstance(a, (int, float)) else (re.findall(r"\d+", a) if isinstance(a, str) and not a.strip() in _options(o) else (a if isinstance(a, list) else []))
        nums = [int(x) for x in vals if isinstance(x, (int, float)) or (isinstance(x, str) and x.isdigit())]
        zero |= 0 in nums
        top |= any(n == len(_options(o)) for n in nums)
    zero_based = True if zero else (False if top else None)
    print(f"answer numbers are {'0-based' if zero_based else '1-based' if zero_based is False else 'not numeric'}")
    items = []
    for i, r in enumerate(rows):
        _, q = _pick(r, Q_KEYS)
        _, o = _pick(r, OPT_KEYS)
        _, a = _pick(r, ANS_KEYS)
        opts = _options(o)
        gold = _answer_set(a, opts, zero_based)
        if not q or len(opts) < 2 or not gold:
            continue
        items.append({"id": str(r.get("id", i)), "area": str(r.get(ck, "all")) if ck else "all", "question": str(q).strip(), "options": opts, "gold": sorted(gold)})
    print(f"dataset: {len(rows)} rows, {len(items)} usable (question + options + answer); area field: {ck or 'none'}")
    return items


def sample(items: list[dict], per: int, areas: list[str] | None, seed: int) -> list[dict]:
    by: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by[it["area"]].append(it)
    rnd = random.Random(seed)
    out = []
    for area in sorted(by):
        if areas and not any(a.lower() in area.lower() for a in areas):
            continue
        pool = sorted(by[area], key=lambda x: x["id"])
        out += pool if per <= 0 else rnd.sample(pool, min(per, len(pool)))
    return out


# ------------------------------------------------------------------------------------------------ asking Sanad
def prompt(it: dict) -> str:
    opts = "\n".join(f"{k}) {o}" for k, o in enumerate(it["options"], start=1))
    return f"{it['question']}\n\nالخيارات:\n{opts}\n\nحدد كل الخيارات الصحيحة (قد يكون أكثر من خيار واحد) واذكر أرقامها، مع السند القانوني."


MAP_SYSTEM = (
    "You answer a multiple-choice question on Moroccan law. Several options may be correct, and a question is scored correct only when "
    "you select exactly the correct options: every wrong option you add, and every correct one you miss, makes it wrong. "
    "You are given the analysis Sanad wrote (each sentence verified against the law) and the articles it retrieved. "
    "The articles are the authority: where they settle an option, follow them, and an option they or the analysis show to be wrong is NOT selected. "
    "Silence is not denial: 'the texts do not mention it' is never a reason to reject an option; then decide with your own knowledge of Moroccan law. "
    "Read by meaning: a standard legal term equals the article's wording for the same thing (التراضي = تعبير صحيح عن الإرادة), and a general "
    "category covers its members. Read every option against the articles before choosing. "
    "Exam convention: when one option says all answers are correct (جميع الأجوبة صحيحة) and every other option is correct, select ONLY that option; "
    "when one option says all answers are wrong and no other option is correct, select only that one. "
    "Return JSON {\"selected\": [option numbers, 1-based]}.")
MAP_SCHEMA = {"type": "object", "properties": {"selected": {"type": "array", "items": {"type": "integer"}}}, "required": ["selected"]}
BASE_SYSTEM = (
    "You answer a multiple-choice question on Moroccan law from your own knowledge. Several options may be correct. "
    "Exam convention: when one option says all answers are correct (جميع الأجوبة صحيحة) and every other option is correct, select ONLY that option. "
    "Return JSON {\"selected\": [option numbers, 1-based]}.")


AS_OF = None  # --date


def ask_sanad(pipe, it: dict) -> dict:
    from legalrag.schemas import PrepareRequest, RunRequest
    t0 = time.monotonic()
    prep = pipe.prepare(PrepareRequest(question=prompt(it), mask=False, as_of=AS_OF))
    out = pipe.run(prep["query_id"], RunRequest(approved=True, review_confirmed=True))
    claims = [c.get("text", "") for c in out.get("claims") or []]
    srcs = out.get("sources") or []
    cited = sorted({x for c in out.get("claims") or [] for x in c.get("sources", [])})
    by_id = {s.get("id"): s for s in srcs}
    used = [by_id[c] for c in cited if c in by_id]
    used += [x for x in srcs if x not in used][:max(0, 8 - len(used))]  # the cited articles first, then the best other ones retrieved
    answer = "\n".join(c for c in claims if c)  # verified claims only: an abstention or a quote-only fallback selects nothing
    return {"status": out.get("status"), "answer": answer,
            "cited": [f"{s.get('law')} — {s.get('article')}" for s in (by_id[c] for c in cited if c in by_id)],
            "passages": [{"law": s.get("law"), "article": s.get("article"), "text": (s.get("text") or s.get("chunk_text") or "")[:1500]} for s in used],
            "seconds": round(time.monotonic() - t0, 1)}


def chosen_from_text(text: str, n: int) -> set[int]:
    """Option numbers Sanad named itself: 'الخيار 2', 'الخياران 1 و3', '(3)', 'الجواب: 1، 4'."""
    got: set[int] = set()
    for m in re.finditer(r"(?:الخيار(?:ات|ان|ين)?|الاختيار(?:ات)?|الجواب(?: الصحيح)?|option[s]?)\s*(?:رقم\s*)?[:：]?\s*((?:\d{1,2}\s*(?:[,،و]|and|et)?\s*)+)", text, re.I):
        got |= {int(x) - 1 for x in re.findall(r"\d{1,2}", m.group(1))}
    return {i for i in got if 0 <= i < n}


def map_with_llm(llm, it: dict, answer: str, passages: list[dict], system: str = MAP_SYSTEM) -> set[int]:
    from legalrag.llm.providers import GenRequest
    payload = {"question": it["question"], "options": {str(k): o for k, o in enumerate(it["options"], start=1)}}
    if system is MAP_SYSTEM:
        payload |= {"answer": answer, "law_passages": passages}
    try:
        res = llm.generate_json(GenRequest(system, payload, MAP_SCHEMA, [], None, kind="summary"))
    except Exception as e:  # noqa: BLE001
        print(f"      (mapping call failed: {str(e)[:120]})")
        return set()
    sel = {int(x) - 1 for x in (res or {}).get("selected", []) if isinstance(x, (int, float)) and 1 <= int(x) <= len(it["options"])}
    return all_correct_rule(sel, it["options"])


ALL_OK = re.compile(r"(?:جميع|كل)\s*(?:ال)?(?:أجوبة|اجوبة|الأجوبة|الاجوبة|ما سبق|ما ذكر|الخيارات)\s*(?:ال)?صحيح|جميع ما سبق|كل ما سبق")
ALL_BAD = re.compile(r"خاطئ|لا شيء|غير صحيح")


def all_correct_rule(sel: set[int], options: list[str]) -> set[int]:
    """MizanQA marks only "جميع الأجوبة صحيحة" when every option is right: picking all the others means picking that one."""
    idx = [i for i, o in enumerate(options) if ALL_OK.search(o)]
    if not idx:
        return sel
    others = {i for i, o in enumerate(options) if i != idx[0] and not ALL_BAD.search(o)}
    return {idx[0]} if others and (others <= sel or idx[0] in sel) else sel


# ------------------------------------------------------------------------------------------------ scoring
def score(sel: set[int], gold: set[int]) -> dict:
    tp, fp, fn = len(sel & gold), len(sel - gold), len(gold - sel)
    f1 = 0.0 if not sel else 2 * tp / (2 * tp + fp + fn)
    return {"acc": int(sel == gold), "f1": round(f1, 3), "partial": round(max(0.0, (tp - fp) / len(gold)), 3)}


def table(results: list[dict], key: str) -> None:
    by: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        if r.get(key):
            by[r["area"]].append(r)
    print(f"\n  {'area':42} {'n':>3} {'ACC':>6} {'F1':>6} {'PARTIAL':>8} {'cited':>6} {'abstained':>9}")
    allr = []
    for area in sorted(by):
        rs = by[area]
        allr += rs
        _row(area, rs, key)
    _row("ALL", allr, key)


def _row(name: str, rs: list[dict], key: str) -> None:
    n = len(rs)
    if not n:
        return
    m = lambda f: sum(r[key][f] for r in rs) / n  # noqa: E731
    cited = sum(1 for r in rs if r.get("sanad", {}).get("cited")) if key == "score" else 0
    abst = sum(1 for r in rs if r.get("sanad", {}).get("status") in ("abstained", "unavailable")) if key == "score" else 0
    print(f"  {name[:42]:42} {n:>3} {m('acc'):>6.0%} {m('f1'):>6.2f} {m('partial'):>8.2f} {cited if key == 'score' else '':>6} {abst if key == 'score' else '':>9}")


# ------------------------------------------------------------------------------------------------ coverage (search only, no model)
NUM_RE = re.compile(r"(?<![\d.])(\d{1,3}\.\d{2})(?![\d.])(?!\s*(?:درهم|دراهم|%))")  # law numbers have 2 digits after the dot: "20.000 درهم" is an amount  # "قانون رقم 103.13", "الظهير 1.58.250" -> "58.250" is caught as part of it below
DAHIR_RE = re.compile(r"(?<![\d.])(\d\.\d{2}\.\d{2,4})(?![\d.])")


def coverage(ctx, todo: list[dict]) -> int:
    """For each question: the law numbers it names (in the pack or not), and what Sanad's search finds for it (law, score, covered)."""
    import sqlite3
    from datetime import date
    from legalrag.pipeline import understand as U
    from legalrag.retrieval.engine import RetrievalRequest
    db = sqlite3.connect(f"file:{ctx.settings.resolved_lawpack_path()}?mode=ro", uri=True)
    today = date.today().isoformat()
    live = {r[0] for r in db.execute("SELECT DISTINCT p.instrument_id FROM provision p JOIN provision_version pv ON pv.provision_id=p.provision_id "
                                      "WHERE pv.valid_from <= ? AND (pv.valid_to IS NULL OR pv.valid_to > ?)", (today, today))}
    by_num: dict[str, list[str]] = defaultdict(list)
    title: dict[str, str] = {}
    for iid, num, t_ar, t_fr in db.execute("SELECT instrument_id, number, title_ar, title_fr FROM instrument"):
        title[iid] = (t_ar or t_fr or iid)[:70]
        if num and iid in live:
            by_num[num.lstrip("0") if re.fullmatch(r"\d+\.\d+", num) else num].append(iid)
    pack = ctx.pack
    rows, named_missing, found_laws = [], defaultdict(list), defaultdict(lambda: defaultdict(int))
    for k, it in enumerate(todo, start=1):
        text = prompt(it)
        nums = set(DAHIR_RE.findall(text))
        rest = DAHIR_RE.sub(" ", text)
        nums |= set(NUM_RE.findall(rest))
        named = []
        for n in sorted(nums):
            key = n.lstrip("0") if re.fullmatch(r"\d+\.\d+", n) else n
            have = by_num.get(key, [])
            named.append({"number": n, "in_pack": bool(have)})
            if not have:
                named_missing[n].append(it["id"])
        try:
            u = U.understand(it["question"], pack, today=ctx.today_fn(), explicit_as_of=AS_OF, max_sub=ctx.settings.max_subquestions)
            ret = ctx.engine.retrieve(RetrievalRequest(query=it["question"] + "\n" + "\n".join(it["options"]), as_of=u.as_of, sub_questions=u.sub_questions,
                                                       domains=u.domains, exact_refs=u.exact_refs, focus_instruments=u.focus_instruments,
                                                       today=ctx.today_fn(), lang="ar"))
            laws: dict[str, float] = {}
            for c in ret.candidates:
                laws[c.chunk.instrument_id] = max(laws.get(c.chunk.instrument_id, 0.0), c.score)
            top = sorted(laws.items(), key=lambda kv: -kv[1])[:3]
            cov_ok, best = ret.coverage.covered, ret.coverage.top_score
            unresolved = [r.get("raw") or str(r) for r in ret.unresolved_refs]
        except Exception as e:  # noqa: BLE001
            top, cov_ok, best, unresolved = [], False, 0.0, [f"error: {str(e)[:100]}"]
        if top:
            found_laws[it["area"]][top[0][0]] += 1
        rows.append({"area": it["area"], "id": it["id"], "covered": cov_ok, "best_score": round(best, 3),
                     "laws_found": [f"{title.get(i, i)} ({s:.2f})" for i, s in top], "top_law": top[0][0] if top else "",
                     "named_numbers": named, "unresolved_refs": unresolved, "question": it["question"]})
        if k % 25 == 0:
            print(f"  {k}/{len(todo)}")
    db.close()

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    REPORTS.mkdir(exist_ok=True)
    with (REPORTS / f"mizanqa_coverage_{stamp}.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["area", "id", "covered", "best_score", "laws_found", "named_not_in_pack", "unresolved_refs", "question"])
        for r in rows:
            w.writerow([r["area"], r["id"], "yes" if r["covered"] else "NO", r["best_score"], " | ".join(r["laws_found"]),
                        " ".join(n["number"] for n in r["named_numbers"] if not n["in_pack"]), " | ".join(r["unresolved_refs"]), r["question"][:300]])
    print(f"\n  {'area':42} {'n':>4} {'covered':>8}   laws Sanad's search lands on most")
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by[r["area"]].append(r)
    for area in sorted(by):
        rs = by[area]
        tops = sorted(found_laws[area].items(), key=lambda kv: -kv[1])[:3]
        print(f"  {area[:42]:42} {len(rs):>4} {sum(r['covered'] for r in rs) / len(rs):>8.0%}   " + "; ".join(f"{title.get(i, i)[:38]} x{n}" for i, n in tops))
    print(f"  {'ALL':42} {len(rows):>4} {sum(r['covered'] for r in rows) / max(1, len(rows)):>8.0%}")
    if named_missing:
        print("\nLAW NUMBERS THE QUESTIONS NAME THAT ARE NOT IN YOUR PACK (number: how many questions)")
        for n, ids in sorted(named_missing.items(), key=lambda kv: -len(kv[1])):
            print(f"  {n:12} {len(ids)}")
    else:
        print("\nevery law number named in these questions is in your pack")
    weak = [r for r in rows if not r["covered"]]
    if weak:
        print(f"\n{len(weak)} question(s) where the search found nothing strong enough (Sanad would abstain): see the rows marked NO in the csv;")
        print("their topic tells you which law to add. First ones:")
        for r in weak[:8]:
            print(f"  [{r['area'][:20]}] {r['question'][:110]}")
    print(f"\nreport: reports\\mizanqa_coverage_{stamp}.csv")
    return 0


# ------------------------------------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--file")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--per", type=int, default=10)
    ap.add_argument("--areas", nargs="*")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--depth", choices=["normal", "deep", "max"], default="normal")
    ap.add_argument("--date", help="YYYY-MM-DD: answer with the law in force on that date")
    ap.add_argument("--coverage", action="store_true", help="search only, no model: which laws the questions need and whether the pack has them")
    a = ap.parse_args()

    global AS_OF
    if a.date:
        from datetime import date as _d
        AS_OF = _d.fromisoformat(a.date)
        print(f"law date: {AS_OF}")
    items = load(a.file)
    if a.list:
        cnt: dict[str, int] = defaultdict(int)
        for it in items:
            cnt[it["area"]] += 1
        for k in sorted(cnt):
            print(f"  {cnt[k]:5}  {k}")
        return 0
    todo = sample(items, a.per, a.areas, a.seed)
    if not todo:
        print("no question matches --areas; run with --list to see the area names")
        return 1
    print(f"sample: {len(todo)} questions ({'all' if a.per <= 0 else a.per} per area, seed {a.seed})")

    from legalrag.config import Settings
    from legalrag.pipeline.orchestrator import QueryPipeline
    from legalrag.state import build_context
    ctx = build_context(Settings())
    if not ctx.pack_usable():
        print("no usable law pack:", ctx.pack_error)
        return 2
    if a.coverage:
        return coverage(ctx, todo)
    llm = ctx.llm()
    if llm is None:
        print("no language model configured: Sanad will answer with quoted passages only, and options can only be read from its text")
    pipe = QueryPipeline(ctx)

    REPORTS.mkdir(exist_ok=True)
    live = REPORTS / "mizanqa_progress.jsonl"
    done: dict[str, dict] = {}
    if a.resume and live.exists():
        for l in live.read_text("utf-8").splitlines():
            r = json.loads(l)
            done[r["id"]] = r
        print(f"resuming: {len(done)} already answered")
    elif live.exists():
        live.unlink()
    results = []
    for k, it in enumerate(todo, start=1):
        if it["id"] in done:
            results.append(done[it["id"]])
            continue
        print(f"[{k}/{len(todo)}] {it['area'][:30]}  {it['question'][:70]}")
        gold = set(it["gold"])
        try:
            s = ask_sanad(pipe, it)
        except Exception as e:  # noqa: BLE001 - one failing question must not stop the run
            s = {"status": f"error: {str(e)[:200]}", "answer": "", "cited": [], "passages": [], "seconds": 0}
        if llm is not None and (s["answer"] or s["passages"]):
            # the choice is made from Sanad's verified analysis + the articles it retrieved (a quote-only fallback still has the articles)
            sel, how = map_with_llm(llm, it, s["answer"], s["passages"]), ("from the answer + articles" if s["answer"] else "from the articles only")
        else:
            sel, how = chosen_from_text(s["answer"], len(it["options"])), "options named in the text"
        if not s["answer"] and not s["passages"]:
            how = "nothing found"
        r = {**it, "sanad": {k2: v for k2, v in s.items() if k2 != "passages"}, "selected": sorted(i + 1 for i in sel), "gold": [g + 1 for g in sorted(gold)],
             "selected_by": how, "score": score(sel, gold)}
        if a.baseline and llm is not None:
            bsel = map_with_llm(llm, it, "", [], system=BASE_SYSTEM)
            r["baseline"] = {"selected": sorted(i + 1 for i in bsel)}
            r["baseline_score"] = score(bsel, gold)
        mark = "OK " if r["score"]["acc"] else "   "
        print(f"      {mark} gold {r['gold']}  sanad {r['selected']}  ({how}, {s['status']}, {s['seconds']}s)" + (f"  model alone {r['baseline']['selected']}" if "baseline" in r else ""))
        with live.open("a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        results.append(r)

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    (REPORTS / f"mizanqa_{stamp}.json").write_text(json.dumps({"dataset": HF_ID, "per_area": a.per, "seed": a.seed, "results": results}, ensure_ascii=False, indent=1), "utf-8")
    with (REPORTS / f"mizanqa_{stamp}.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["area", "id", "acc", "f1", "partial", "gold", "sanad", "selected_by", "status", "cited", "question"])
        for r in results:
            w.writerow([r["area"], r["id"], r["score"]["acc"], r["score"]["f1"], r["score"]["partial"], r["gold"], r["selected"], r["selected_by"],
                        r["sanad"]["status"], " | ".join(r["sanad"]["cited"]), r["question"][:200]])
    print("\nSANAD (law pack + model)")
    table(results, "score")
    if a.baseline:
        print("\nTHE MODEL ALONE (no law pack)")
        table(results, "baseline_score")
    print(f"\nreport: reports\\mizanqa_{stamp}.json  and .csv")
    print("note: a small sample is a rough signal (10 questions = +/- about 15 points); compare runs with the same --seed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
