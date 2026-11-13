"""Load builder sources from a directory of YAML / JSON files. Lists (sources, instruments, provisions,
edges, transitional_rules, rates, deadline_rules, holidays, decisions, pending_bills, concordance) are concatenated;
scalar keys (e.g. last_bo_check) take the last value."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

LIST_KEYS = ["sources", "instruments", "provisions", "edges", "transitional_rules", "rates", "deadline_rules", "holidays", "decisions", "pending_bills", "concordance"]


def load_sources(path: Path) -> dict:
    files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.suffix.lower() in {".yaml", ".yml", ".json"})
    out: dict = {k: [] for k in LIST_KEYS}
    for f in files:
        data = yaml.safe_load(f.read_text("utf-8")) if f.suffix.lower() in {".yaml", ".yml"} else json.loads(f.read_text("utf-8"))
        for k, v in (data or {}).items():
            if k in LIST_KEYS:
                out[k].extend(v or [])
            else:
                out[k] = v
    return out
