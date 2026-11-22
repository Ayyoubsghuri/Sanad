"""Sanad as a desktop application: the backend and the interface in ONE window, without a browser and without a console.

    pythonw -m legalrag.desktop --app-dir "C:\\...\\Sanad"      (what Sanad.exe runs; needs: pip install legalrag-backend[desktop])

The window has no Windows title bar: the interface draws its own minimise / maximise / close buttons and its top bar moves the
window (--native-frame brings the standard title bar back).  The backend still listens on 127.0.0.1 only."""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

LOADING = """<!doctype html><html><body class="pywebview-drag-region" style="margin:0;height:100vh;display:flex;flex-direction:column;
align-items:center;justify-content:center;background:#f4f3f0;color:#111;font-family:Segoe UI,sans-serif;user-select:none">
<svg width="84" height="84" viewBox="0 0 256 256"><circle cx="128" cy="30" r="14" fill="#111"/>
<rect x="28" y="56" width="200" height="176" rx="78" fill="#111"/><circle cx="92" cy="146" r="30" fill="#fff"/>
<circle cx="164" cy="146" r="30" fill="#fff"/></svg>
<div style="margin-top:18px;font-size:22px;font-weight:600">Sanad</div>
<div id="m" style="margin-top:8px;font-size:13px;color:#666">Loading the law pack and the models...</div></body></html>"""


class WindowApi:
    """Called by the interface (window.pywebview.api.*) for its own window buttons."""

    def __init__(self) -> None:
        self._window = None
        self._maximized = False

    def minimize(self) -> None:
        self._window.minimize()

    def toggle_maximize(self) -> bool:
        (self._window.restore if self._maximized else self._window.maximize)()
        self._maximized = not self._maximized
        return self._maximized

    def resize(self, width: int, height: int) -> None:
        if not self._maximized:
            self._window.resize(max(900, int(width)), max(600, int(height)))

    def close(self) -> None:
        self._window.destroy()

    def save_file(self, name: str, base64_data: str) -> str:
        """A file made by the page (Word, Markdown, PDF...): the window cannot download it itself, so Windows' "Save as"
        dialog asks where, the file is written there and its folder is opened. Returns the path, "" if cancelled,
        "error: ..." on failure."""
        import base64

        import webview

        try:
            safe = "".join("_" if c in '\\/:*?"<>|' else c for c in (name or "sanad")).strip() or "sanad"
            downloads = Path.home() / "Downloads"
            save = getattr(webview, "SAVE_DIALOG", None)
            if save is None:  # pywebview 6 names it FileDialog.SAVE
                save = webview.FileDialog.SAVE
            got = self._window.create_file_dialog(save, directory=str(downloads if downloads.is_dir() else Path.home()),
                                                  save_filename=safe)
            if not got:
                return ""
            path = Path(got if isinstance(got, str) else got[0])
            path.write_bytes(base64.b64decode(base64_data))
            if sys.platform == "win32":
                import subprocess

                subprocess.Popen(["explorer", "/select,", str(path)])  # noqa: S603,S607 - shows the saved file in its folder
            return str(path)
        except Exception as e:  # noqa: BLE001 - shown in the page
            return f"error: {e}"


def _healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(url + "/health", timeout=2) as r:  # noqa: S310 - loopback only
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def _serves_page(url: str) -> bool:
    """A backend started by hand for development (`legalrag`) answers /health but has no app page: it cannot be reused."""
    try:
        with urllib.request.urlopen(url + "/", timeout=3) as r:  # noqa: S310 - loopback only
            return r.status == 200 and "text/html" in (r.headers.get("content-type") or "")
    except Exception:  # noqa: BLE001
        return False


def _free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sk:
        sk.bind(("127.0.0.1", 0))
        return sk.getsockname()[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="legalrag.desktop")
    ap.add_argument("--app-dir", help="the installed application folder (holds backend/pack_release.json and frontend/)")
    ap.add_argument("--native-frame", action="store_true", help="keep the standard Windows title bar")
    a = ap.parse_args(argv)

    if a.app_dir:
        app_dir = Path(a.app_dir)
        release = app_dir / "backend" / "pack_release.json"
        if release.exists():  # only a pack signed by the publisher is accepted
            key = json.loads(release.read_text(encoding="utf-8")).get("public_key_hex")
            if key:
                os.environ.setdefault("LEGALRAG_LAWPACK_PUBLIC_KEY_HEX", key)
        os.environ.setdefault("LEGALRAG_FRONTEND_DIR", str(app_dir / "frontend"))

    # the choice made in the setup window: local models, or search by meaning through Cloudflare (no models installed)
    choice = Path(os.environ.get("LOCALAPPDATA", "")) / "Sanad" / "compute.json"
    if os.environ.get("LOCALAPPDATA") and choice.exists():
        try:
            src = json.loads(choice.read_text(encoding="utf-8-sig")).get("embeddings")
            if src in ("local", "cloudflare"):
                os.environ.setdefault("LEGALRAG_EMBEDDINGS_SOURCE", src)
        except (OSError, ValueError):
            pass

    from .config import Settings

    s = Settings()
    if sys.stdout is None or sys.stderr is None:  # pythonw has no console: keep the messages in a file
        logs = s.data_dir / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        sys.stdout = sys.stderr = open(logs / "desktop.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115

    try:
        import webview
    except ImportError:
        print("Missing package. Run:  pip install legalrag-backend[desktop]", file=sys.stderr)
        return 2

    url = f"http://127.0.0.1:{s.port}"
    frameless = not a.native_frame
    state: dict = {"server": None, "error": None, "settings": s}

    def serve() -> None:
        try:
            import uvicorn

            from .main import create_app
            from .state import build_context

            cfg = state["settings"]
            server = uvicorn.Server(uvicorn.Config(create_app(cfg, build_context(cfg)), host=cfg.host, port=cfg.port, log_level="info"))
            state["server"] = server
            server.run()
        except BaseException as e:  # noqa: BLE001 - shown in the window, the process must not die silently
            state["error"] = f"{type(e).__name__}: {e}"
            import traceback

            traceback.print_exc()

    def boot(window) -> None:
        nonlocal url
        thread = None
        if _healthy(url) and not _serves_page(url):
            # another backend holds the port without the app page (e.g. `legalrag` started by hand for the web version):
            # leave it alone and run Sanad's own on a free port, instead of showing {"detail": "Not Found"}
            port = _free_port()
            state["settings"] = s.model_copy(update={"port": port})
            url = f"http://127.0.0.1:{port}"
            print(f"port {s.port} is used by a backend without the app page: Sanad uses port {port}")
        if not _healthy(url):  # (a backend that already serves the app, e.g. a second start, is simply reused)
            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
        for _ in range(600):
            if _healthy(url):
                window.load_url(url + ("/?shell=frameless" if frameless else "/"))
                return
            if state["error"] or (thread and not thread.is_alive()):
                break
            time.sleep(0.5)
        msg = (state["error"] or "the backend did not start").replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")
        window.evaluate_js(f"document.getElementById('m').textContent = 'Sanad could not start: {msg}'")
        time.sleep(15)
        window.destroy()

    if sys.platform == "win32":  # its own taskbar button with the Sanad icon (not the Python one)
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Sanad.Desktop")
        except Exception:  # noqa: BLE001
            pass

    api = WindowApi()
    window = webview.create_window("Sanad", html=LOADING, js_api=api, width=1360, height=860, min_size=(900, 600),
                                   frameless=frameless, easy_drag=False, text_select=True, background_color="#F4F3F0")
    api._window = window
    icon = Path(a.app_dir) / "app.ico" if a.app_dir else None
    storage = s.data_dir / "window"  # keeps the interface's own settings and chat list between starts
    storage.mkdir(parents=True, exist_ok=True)
    webview.start(boot, (window,), private_mode=False, storage_path=str(storage), icon=str(icon) if icon and icon.exists() else None)
    if state["server"] is not None:
        state["server"].should_exit = True
        time.sleep(1.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
