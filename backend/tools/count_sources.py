"""Count everything the installed pack was built from: source files (PDFs) and pages, by kind -- laws, codes, BOCT and Bulletin Officiel (BO) pages.

    py tools\\count_sources.py
Pages = the highest page number cited by any article of that source (a lower bound: pages with no article text are not counted)."""
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from legalrag.config import Settings  # noqa: E402

db = sqlite3.connect(f"file:{Settings().resolved_lawpack_path()}?mode=ro", uri=True)
rows = db.execute(
    "SELECT s.source_id, s.kind, s.label, i.instrument_id, i.bo_number, COALESCE(MAX(l.page_end),0) "
    "FROM source_file s LEFT JOIN provision_version pv ON pv.source_id=s.source_id "
    "LEFT JOIN provision p ON p.provision_id=pv.provision_id LEFT JOIN instrument i ON i.instrument_id=p.instrument_id "
    "LEFT JOIN provision_page l ON l.provision_id=p.provision_id AND l.source_id=s.source_id GROUP BY s.source_id").fetchall()
groups: dict[str, list] = defaultdict(list)
for sid, kind, label, iid, bo, pages in rows:
    g = "BOCT issues" if (iid or "").startswith("MA_BOCT_") else ("Bulletin Officiel (BO)" if kind == "bo_pdf" else "laws / codes / decrees")
    groups[g].append(pages or 0)
tot_f = tot_p = 0
for g, v in sorted(groups.items()):
    print(f"{g:28} files={len(v):4}  pages={sum(v):6}")
    tot_f += len(v)
    tot_p += sum(v)
print(f"{'TOTAL':28} files={tot_f:4}  pages={tot_p:6}")
