"""Find articles that the importer glued into the article before them (a heading it did not recognise, e.g. «المادة82» with no space).

    py tools\\check_glued_articles.py              report only: per law, which articles hold the heading of another article inside their text

An article that is glued is invisible to the search and to «الفصل 82»: the pack answers «art. 82: not found».  The cause is repaired in the
importer (headings with no space are now read); the laws listed here must be IMPORTED AGAIN to get their articles apart.  Nothing is changed."""
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
from legalrag.config import Settings
from legalrag.store.lawpack import LawPack

EMBEDDED = re.compile(r"(?:^|\n)\s*(?:المادة|الفصل)\s*(\d+(?:-\d+)?)\s*(?=\n|$|[^\d\s])", re.M)

pack = LawPack(Settings().resolved_lawpack_path())
rows = pack._q(
    "SELECT p.instrument_id AS iid, p.number AS num, pt.text AS text FROM provision p JOIN provision_version pv ON pv.provision_id=p.provision_id "
    "JOIN provision_text pt ON pt.pv_id=pv.pv_id WHERE pv.valid_to IS NULL AND pt.lang='ar' AND (pt.text LIKE '%المادة%' OR pt.text LIKE '%الفصل%')"
)
have: dict[str, set[str]] = defaultdict(set)
for r in pack._q("SELECT instrument_id AS iid, number AS num FROM provision"):
    have[r["iid"]].add(str(r["num"]))
found: dict[str, list[tuple[str, str, bool]]] = defaultdict(list)
for r in rows:
    body = r["text"]
    for m in EMBEDDED.finditer(body):
        if m.start() < 3:
            continue  # the heading of the article itself
        found[r["iid"]].append((str(r["num"]), m.group(1), m.group(1) in have[r["iid"]]))
tot = sum(len(v) for v in found.values())
print(f"{tot} embedded heading(s) in {len(found)} law(s)\n")
for iid, v in sorted(found.items(), key=lambda kv: -len(kv[1])):
    missing = [e for _, e, ok in v if not ok]
    print(f"{iid:28} {len(v):4} embedded   {len(missing):4} of them have no article of their own   e.g. art. {v[0][0]} holds «المادة {v[0][1]}»")
print("\nOnly the ones 'with no article of their own' are lost; the others are probably a cross-reference printed on its own line.")
