"""BO / SGG watcher (build side): re-fetch listed official URLs, compare SHA-256 with the last seen hash and
report new / changed / unreachable pages so affected instruments can be re-ingested into the next pack."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx


def watch(targets: list[dict], state_path: Path, client: httpx.Client | None = None) -> dict:
    client = client or httpx.Client(timeout=30, follow_redirects=True)
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    report = {"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "new": [], "changed": [], "unchanged": [], "unreachable": []}
    for t in targets:
        name, url = t["name"], t["url"]
        try:
            r = client.get(url)
            r.raise_for_status()
        except httpx.HTTPError as e:
            report["unreachable"].append({"name": name, "url": url, "error": e.__class__.__name__})
            continue
        h = hashlib.sha256(r.content).hexdigest()
        prev = state.get(name, {}).get("sha256")
        bucket = "new" if prev is None else ("unchanged" if prev == h else "changed")
        report[bucket].append({"name": name, "url": url, "sha256": h})
        state[name] = {"sha256": h, "url": url, "seen_at": report["checked_at"]}
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2))
    return report
