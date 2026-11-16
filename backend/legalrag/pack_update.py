"""Check for, download and install the published law pack from inside the app (the "Law pack" panel of the update window).

The published pack is described by pack_release.json on the repository's main branch (version, size, SHA-256, download
addresses, publisher key). A download is only installed when its SHA-256 matches AND its signature verifies against the
publisher key this machine already trusts (LEGALRAG_LAWPACK_PUBLIC_KEY_HEX); a different key in the published file is
refused, so a changed web page cannot make the app accept a pack from someone else. Only one pack is kept on disk:
the new one replaces the old one. An interrupted download continues where it stopped the next time."""
from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .state import AppContext, install_pack
from .store.lawpack import PackError
from .store.signing import sha256_file

UA = {"User-Agent": "Sanad-law-pack-updater"}
_STAMP = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})(?:\.(\d{4}))?")


def _stamp(version: str | None) -> str:
    """The build time at the start of a pack version ("2026.11.08.1455-retire" -> "202611081455"), "" when there is none."""
    m = _STAMP.match(version or "")
    return "".join(g or "0000" for g in m.groups()) if m else ""


class PackUpdater:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self.job: dict[str, Any] | None = None
        self._lock = threading.Lock()
        self._cancel = threading.Event()

    # ---- what is published -------------------------------------------------------------------------------------------
    def _release(self, client: httpx.Client | None = None) -> dict[str, Any]:
        url = self.ctx.settings.pack_release_url
        c = client or httpx.Client(timeout=20, follow_redirects=True, headers=UA)
        try:
            r = c.get(url)
            r.raise_for_status()
            info = r.json()
        finally:
            if client is None:
                c.close()
        for k in ("pack_version", "sha256", "db_url", "sig_url", "public_key_hex"):
            if not info.get(k):
                raise PackError(f"the published pack description has no '{k}'")
        for k in ("db_url", "sig_url"):
            if not str(info[k]).startswith("https://"):
                raise PackError(f"refusing a non-https download address: {info[k]}")
        return info

    def problems(self) -> list[str]:
        out = []
        if self.ctx.mode == "offline":
            out.append("The app is in offline mode: switch to hybrid mode to check for a new law pack.")
        if not self.ctx.settings.lawpack_public_key_hex:
            out.append("No publisher key is set (LEGALRAG_LAWPACK_PUBLIC_KEY_HEX): a downloaded pack could not be verified.")
        return out

    def check(self) -> dict[str, Any]:
        """Installed version vs published version. Nothing is downloaded."""
        pack = self.ctx.pack
        installed = pack.version if pack else None
        res: dict[str, Any] = {"installed_version": installed, "installed_built_at": pack.built_at if pack else None,
                               "problems": self.problems(), "job": self.job, "checked_at": datetime.now(timezone.utc).isoformat()}
        if res["problems"]:
            return res
        try:
            info = self._release()
        except (httpx.HTTPError, ValueError, PackError) as e:
            res["error"] = f"could not read the published pack description: {e}"
            return res
        published = info["pack_version"]
        res.update(published_version=published, size_bytes=info.get("size_bytes"),
                   key_matches=info["public_key_hex"].lower() == (self.ctx.settings.lawpack_public_key_hex or "").lower())
        if installed == published:
            res["update_available"] = False
        elif not installed:
            res["update_available"] = True
        else:  # newer build time = newer pack; a pack updated here with new BO issues keeps its own, later, time
            res["update_available"] = _stamp(published) > _stamp(installed)
        return res

    # ---- download + install (background job) -------------------------------------------------------------------------
    def start(self) -> dict[str, Any]:
        with self._lock:
            if self.job and self.job["state"] in ("queued", "running"):
                return self.job
            probs = self.problems()
            if probs:
                raise PackError(" ".join(probs))
            bo = getattr(getattr(self.ctx, "bo_updater", None), "job", None)
            if bo is not None and bo.state in ("queued", "running"):
                raise PackError("a Bulletin Officiel update is running: wait until it finishes")
            self._cancel.clear()
            self.job = {"state": "queued", "step": "check", "detail": "", "done_bytes": 0, "total_bytes": 0, "progress": 0.0,
                        "error": None, "installed_version": None, "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None}
            threading.Thread(target=self._run, daemon=True, name="pack-update").start()
            return self.job

    def cancel(self) -> bool:
        self._cancel.set()
        return bool(self.job and self.job["state"] in ("queued", "running"))

    def _set(self, **kw: Any) -> None:
        if self.job is not None:
            self.job.update(kw)

    def _fetch(self, client: httpx.Client, url: str, dest: Path, weight: tuple[float, float]) -> None:
        """Download with resume. weight = (start, share) of the overall progress bar."""
        for attempt in range(1, 9):
            have = dest.stat().st_size if dest.exists() else 0
            headers = {"Range": f"bytes={have}-"} if have else {}
            try:
                with client.stream("GET", url, headers=headers) as r:
                    if r.status_code == 416:  # already complete
                        return
                    r.raise_for_status()
                    if have and r.status_code != 206:  # the server ignored the range: start again
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
                                share = have / total if total else 0
                                self._set(done_bytes=have, progress=round(weight[0] + weight[1] * share, 4))
                self._set(done_bytes=have)
                return
            except (httpx.HTTPError, OSError) as e:
                if attempt == 8:
                    raise PackError(f"download failed ({e}); click again to continue where it stopped") from e
                self._set(detail=f"connection lost, retrying ({attempt}/8)")
                time.sleep(min(30, 2 * attempt))

    def _run(self) -> None:
        ctx = self.ctx
        tmp = ctx.settings.data_dir / "download"
        tmp.mkdir(parents=True, exist_ok=True)  # kept between attempts so a download can continue
        db, sig = tmp / "current.db", tmp / "current.db.sig"
        try:
            self._set(state="running", step="check", detail="reading the published pack description")
            with httpx.Client(timeout=httpx.Timeout(60, connect=20), follow_redirects=True, headers=UA) as client:
                info = self._release(client)
                if info["public_key_hex"].lower() != (ctx.settings.lawpack_public_key_hex or "").lower():
                    raise PackError("the published pack is signed with a different key than the one this app trusts: not installed")
                if ctx.pack and ctx.pack.version == info["pack_version"]:
                    self._set(state="done", step="install", progress=1.0, detail="already up to date",
                              installed_version=info["pack_version"])
                    return
                self._set(step="download", detail=f"pack {info['pack_version']}")
                self._fetch(client, info["db_url"], db, (0.0, 0.85))
                sig.unlink(missing_ok=True)
                self._fetch(client, info["sig_url"], sig, (0.85, 0.01))
            self._set(step="verify", detail="checking the SHA-256 and the publisher's signature", progress=0.87)
            if sha256_file(db) != info["sha256"]:
                db.unlink(missing_ok=True)  # damaged or an older partial file: the next attempt starts again
                raise PackError("the download does not match the published SHA-256: not installed (click again to download it again)")
            if self._cancel.is_set():
                raise InterruptedError
            self._set(step="install", detail="replacing the law pack", progress=0.92)
            if ctx.pack:  # Windows cannot overwrite an open file
                ctx.pack.close()
                ctx.pack = None
            res = install_pack(ctx, db, sig)
            for p in (db, sig):
                p.unlink(missing_ok=True)
            self._set(state="done", progress=1.0, detail="installed", installed_version=res.get("pack_version"))
        except InterruptedError:
            self._set(state="cancelled", detail="stopped; click again to continue the download")
        except Exception as e:  # noqa: BLE001 - shown in the app
            if ctx.pack is None:
                ctx.load_pack()  # put the previous pack back in service
            self._set(state="error", error=str(e))
        finally:
            self._set(finished_at=datetime.now(timezone.utc).isoformat())

