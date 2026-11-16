"""Writes the toolkit (catalog, prompts, schemas) as one JSON file for the phone app, which runs the same tools in Java.

    python -m legalrag.pro.export ../mobile/android/web-extra/pro_toolkit.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import catalog as C
from . import engine as E


def payload() -> dict:
    return {
        "version": 1,
        "groups": C.GROUPS, "tools": C.TOOLS, "steps": E.STEP_LABELS,
        "prompts": {"base": E.BASE_SYSTEM, "plan": E.PLAN_SYSTEM, "lawyer_a": E.LAWYER_A_SYSTEM, "lawyer_b": E.LAWYER_B_SYSTEM,
                    "judge": E.JUDGE_SYSTEM, "report": E.REPORT_SYSTEM, "finder": E.FINDER_SYSTEM},
        "schemas": {"plan": E.PLAN_SCHEMA, "report": E.REPORT_SCHEMA, "lawyer_a": E.LAWYER_A_SCHEMA, "lawyer_b": E.LAWYER_B_SCHEMA, "judge": E.JUDGE_SCHEMA},
        "side": E.SIDE_TXT, "lang_name": E.LANG_NAME,
        "notice": {"ar": "سند أداة مساعدة على القراءة وليس استشارة قانونية. تحقق من النصوص الرسمية.",
                   "fr": "Sanad est une aide à la lecture, pas un conseil juridique. Vérifiez les textes officiels.",
                   "en": "Sanad is a reading aid, not legal advice. Check the official texts."},
    }


def text() -> str:
    return json.dumps(payload(), ensure_ascii=False, indent=1, sort_keys=True) + "\n"


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[3] / "mobile/android/web-extra/pro_toolkit.json"
    out.write_text(text(), encoding="utf-8")
    print(f"wrote {out}")
