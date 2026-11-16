"""Download and install the published rulings database (Professional Toolkit -> "Download court rulings").

manifest.json (next to rulings.db in the Hugging Face dataset) gives the version, size and SHA-256. The download is
installed only when its SHA-256 matches; it is saved under its own name (rulings-<version>.db) and current.txt points
to it, so an open database is never overwritten (Windows refuses that). An interrupted download continues."""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from ..store.signing import sha256_file
from .rulings import installed_version

UA = {"User-Agent": "Sanad-rulings-updater"}
_VERSION = re.compile(r"^[0-9][0-9A-Za-z.\-]{0,40}$")


class RulingsError(Exception):
    pass


class RulingsUpdater:
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.job: dict[str, Any] | None = None
        self._lock = threading.Lock()
        self._cancel = threading.Event()

    @property
    def folder(self) -> Path:
        return self.ctx.settings.data_dir / "rulings"

    def _manifest(self, client: httpx.Client | None = None) -> dict[str, Any]:
        c = client or httpx.Client(timeout=20, follow_redirects=True, headers=UA)
        try:
            r = c.get(self.ctx.settings.rulings_manifest_url)
            if r.status_code == 404:
                raise RulingsError("no rulings database has been published yet")
            r.raise_for_status()
            info = r.json()
        finally:
            if client is None:
                c.close()
        for k in ("version", "sha256", "db_url"):
            if not info.get(k):
                raise RulingsError(f"the published description has no '{k}'")
        if not str(info["db_url"]).startswith("https://") or not _VERSION.match(str(info["version"])):
            raise RulingsError("the published description is not valid")
        return info

    def check(self) -> dict[str, Any]:
        inst = installed_version(self.ctx.settings.data_dir)
        res: dict[str, Any] = {"installed_version": inst, "job": self.job}
        if self.ctx.mode == "offline":
            res["problem"] = "offline"
            return res
        try:
            info = self._manifest()
        except (httpx.HTTPError, ValueError, RulingsError) as e:
            res["error"] = str(e)
            return res
        res.update(published_version=info["version"], size_bytes=info.get("size_bytes"), rulings=info.get("rulings"),
                   period={"from": info.get("from"), "to": info.get("to")},
                   update_available=inst is None or (inst != "local" and str(info["version"]) > inst))
        return res

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self.job and self.job["state"] in ("queued", "running"):
                return self.job
            if self.ctx.mode == "offline":
                raise RulingsError("the app is in Offline mode: switch to Hybrid mode to download the rulings")
            self._cancel.clear()
            self.job = {"state": "queued", "step": "check", "done_bytes": 0, "total_bytes": 0, "progress": 0.0, "error": None,
                        "version": None, "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None}
            threading.Thread(target=self._run, daemon=True, name="rulings-update").start()
            return self.job

    def cancel(self) -> bool:
        self._cancel.set()
        return bool(self.job and self.job["state"] in ("queued", "running"))

    def _set(self, **kw: Any) -> None:
        if self.job is not None:
            self.job.update(kw)

    def _fetch(self, client: httpx.Client, url: str, dest: Path) -> None:
        for attempt in range(1, 9):
            have = dest.stat().st_size if dest.exists() else 0
            try:
                with client.stream("GET", url, headers={"Range": f"bytes={have}-"} if have else {}) as r:
                    if r.status_code == 416:
                        return
                    r.raise_for_status()
                    if have and r.status_code != 206:
                        have = 0
                    total = have + int(r.headers.get("content-length") or 0)
                    self._set(total_bytes=total)
                    with open(dest, "ab" if have else "wb") as f:
                        last = 0.0
                        for chunk in r.iter_bytes(1 << 20):
                            if self._cancel.is_set():
                                raise InterruptedError
                            f.write(chunk)
                            have += len(chunk)
                            if time.monotonic() - last > 0.5:
                                last = time.monotonic()
                                self._set(done_bytes=have, progress=round(0.95 * have / total, 4) if total else 0.0)
                self._set(done_bytes=have)
                return
            except (httpx.HTTPError, OSError) as e:
                if attempt == 8:
                    raise RulingsError(f"download failed ({e}); click again to continue where it stopped") from e
                time.sleep(min(30, 2 * attempt))

    def _run(self) -> None:
        tmp = self.ctx.settings.data_dir / "download"
        tmp.mkdir(parents=True, exist_ok=True)
        part = tmp / "rulings.db.part"
        try:
            self._set(state="running", step="check")
            with httpx.Client(timeout=httpx.Timeout(60, connect=20), follow_redirects=True, headers=UA) as client:
                info = self._manifest(client)
                if installed_version(self.ctx.settings.data_dir) == info["version"]:
                    self._set(state="done", progress=1.0, version=info["version"])
                    return
                marker = tmp / "rulings.version"
                if marker.exists() and marker.read_text().strip() != info["version"]:
                    part.unlink(missing_ok=True)       # a partial file of an older version
                marker.write_text(info["version"])
                self._set(step="download", version=info["version"])
                self._fetch(client, info["db_url"], part)
            self._set(step="verify", progress=0.96)
            if sha256_file(part) != info["sha256"]:
                part.unlink(missing_ok=True)
                raise RulingsError("the download does not match the published SHA-256: not installed (click again to download it again)")
            self.folder.mkdir(parents=True, exist_ok=True)
            name = f"rulings-{info['version']}.db"
            part.replace(self.folder / name)
            (self.folder / "current.txt").write_text(name, encoding="utf-8")
            for old in self.folder.glob("rulings-*.db"):   # earlier downloads; one still open is left for next time
                if old.name != name:
                    try:
                        old.unlink()
                    except OSError:
                        pass
            self._set(state="done", step="install", progress=1.0)
        except InterruptedError:
            self._set(state="cancelled")
        except Exception as e:  # noqa: BLE001 - shown in the app
            self._set(state="error", error=str(e))
        finally:
            self._set(finished_at=datetime.now(timezone.utc).isoformat())


_UPDATERS: dict[int, RulingsUpdater] = {}


def updater(ctx) -> RulingsUpdater:
    u = _UPDATERS.get(id(ctx))
    if u is None:
        u = _UPDATERS[id(ctx)] = RulingsUpdater(ctx)
    return u
