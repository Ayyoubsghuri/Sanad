"""Print the last calls sent to the language model with status, error and time taken (no question text).   py tools\\last_errors.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from legalrag.config import Settings  # noqa: E402
from legalrag.state import build_context  # noqa: E402

ctx = build_context(Settings())
for r in ctx.db.list_outbound(15):
    print(r.get("id"), r.get("created_at") or r.get("ts"), r.get("kind"), r.get("provider"), r.get("model"), r.get("status"), r.get("error"), f"{r.get('latency_ms')}ms", f"{r.get('bytes')}B")
