"""Install the search models from inside the app (API keys -> Search by meaning), instead of "Sanad - repair setup".

  small: the small multilingual reranker (~0.5 GB + its libraries), for computers that search by meaning through Cloudflare
  full:  the local models (bge-m3 + bge-reranker-v2-m3, ~4.5 GB + libraries); only with 16 GB of memory or more

Steps, each a child process whose last output line is shown: (1) the Python libraries (sentence-transformers) if missing,
with the installer's own uv when the app was installed, else pip; (2) python -m legalrag.fetch_models. A stopped download
continues where it stopped the next time."""
from __future__ import annotations

import importlib
import importlib.util
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class InstallError(Exception):
    pass


def _lib_command() -> list[str]:
    """How to add sentence-transformers to the running Python."""
    app = os.environ.get("LEGALRAG_APP_DIR")
    uv = Path(app) / "bin" / ("uv.exe" if sys.platform == "win32" else "uv") if app else None
    if uv and uv.exists() and (Path(app) / "backend").exists():
        return [str(uv), "pip", "install", "--python", sys.executable, f"{Path(app) / 'backend'}[local-models]"]
    found = shutil.which("uv")
    if found:
        return [found, "pip", "install", "--python", sys.executable, "sentence-transformers>=3.0"]
    return [sys.executable, "-m", "pip", "install", "sentence-transformers>=3.0"]


def commands(what: str) -> list[tuple[str, list[str]]]:
    steps: list[tuple[str, list[str]]] = []
    if importlib.util.find_spec("sentence_transformers") is None:
        steps.append(("libraries", _lib_command()))
    fetch = [sys.executable, "-m", "legalrag.fetch_models"] + (["--small-reranker"] if what == "small" else ["--pack-embedder"])
    steps.append(("models", fetch))
    return steps


class ModelInstaller:
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.job: dict[str, Any] | None = None
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._cancel = False

    def start(self, what: str, low_ram: bool) -> dict[str, Any]:
        with self._lock:
            if self.job and self.job["state"] in ("queued", "running"):
                return self.job
            if what not in ("small", "full"):
                raise InstallError("unknown model set")
            if self.ctx.mode == "offline":
                raise InstallError("Offline mode: switch to Hybrid to download the models")
            if what == "full" and low_ram:
                raise InstallError("the local models need 16 GB of memory: install the small model instead")
            self._cancel = False
            self.job = {"state": "queued", "what": what, "step": "", "detail": "", "error": None,
                        "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None}
            threading.Thread(target=self._run, args=(what,), daemon=True, name="model-install").start()
            return self.job

    def cancel(self) -> bool:
        self._cancel = True
        p = self._proc
        if p and p.poll() is None:
            p.kill()
        return bool(self.job and self.job["state"] in ("queued", "running"))

    def _run(self, what: str) -> None:
        job = self.job
        assert job is not None
        try:
            job["state"] = "running"
            env = {**os.environ, "PYTHONUNBUFFERED": "1", "HF_HUB_DISABLE_PROGRESS_BARS": "1", "PYTHONUTF8": "1"}
            for step, cmd in commands(what):
                job.update(step=step, detail="")
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                              errors="replace", env=env, creationflags=flags)
                last = ""
                for line in self._proc.stdout:   # type: ignore[union-attr]
                    line = line.strip()
                    if line:
                        last = line
                        job["detail"] = line[-200:]
                code = self._proc.wait()
                if self._cancel:
                    raise InterruptedError
                if code != 0:
                    raise InstallError(f"{step} did not finish ({last[-200:] or f'exit {code}'}); click again to continue")
            importlib.invalidate_caches()
            ctx = self.ctx
            ctx._small_reranker, ctx._small_reranker_failed = None, False   # loaded on the next question
            ctx._local_reranker, ctx._local_embedder = None, None
            if what == "full":
                ctx.db.set_settings({"embeddings_source": "local"})
            job.update(state="done", detail="installed")
        except InterruptedError:
            job.update(state="cancelled", detail="stopped; click again to continue")
        except Exception as e:  # noqa: BLE001 - shown in the app
            job.update(state="error", error=str(e))
        finally:
            self._proc = None
            job["finished_at"] = datetime.now(timezone.utc).isoformat()


_INSTALLERS: dict[int, ModelInstaller] = {}


def installer(ctx) -> ModelInstaller:
    return _INSTALLERS.setdefault(id(ctx), ModelInstaller(ctx))
