"""The "check for new Bulletin Officiel" job: find -> download -> extract -> parse -> embed -> install, with live progress.

One job at a time, in a background thread (the UI polls GET /v1/bo/update).  The running pack is never modified: new text is appended to a
COPY of it, which is signed (when the pack is signed) and verified before install_pack puts it in place of the current one."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..builder import checks
from ..builder.append import AppendError, append_sources
from ..builder.from_bo import bo_to_sources, freeze_pdfs
from ..builder.pipeline_import import PipelineImportError, load_pipeline_chunks
from ..state import AppContext, install_pack
from ..store.localkey import effective_public_key, local_private_key, public_from_private
from ..store.lawpack import PackError
from ..text.cleanup import Cleaner
from . import discover

STEPS = [("check", "Looking for new issues on the SGG site"), ("download", "Downloading"), ("extract", "Reading the PDFs"),
         ("ingest", "Splitting into articles and indexing"), ("install", "Installing the updated law pack")]


class Cancelled(Exception):
    pass


class BoJob:
    def __init__(self, dry_run: bool = False):
        self.id = uuid.uuid4().hex[:10]
        self.dry_run = dry_run
        self.state = "queued"  # queued | running | done | error | cancelled
        self.steps = [{"id": i, "label": l, "status": "pending", "done": 0, "total": 0, "detail": ""} for i, l in STEPS]
        self.found: list[dict] = []
        self.added: dict = {}
        self.warnings: list[str] = []
        self.log: list[str] = []
        self.error: str | None = None
        self.started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.finished_at: str | None = None
        self.cancel = threading.Event()

    def step(self, sid: str) -> dict:
        return next(s for s in self.steps if s["id"] == sid)

    def to_dict(self) -> dict:
        n = len(self.steps)
        frac = 0.0
        for s in self.steps:
            frac += 1.0 if s["status"] in ("done", "skipped") else ((s["done"] / s["total"]) if s["total"] and s["status"] == "running" else 0.0)
        return {"id": self.id, "state": self.state, "dry_run": self.dry_run, "progress": round(frac / n, 3), "steps": self.steps, "found": self.found,
                "added": self.added, "warnings": self.warnings[-30:], "log": self.log[-40:], "error": self.error, "started_at": self.started_at, "finished_at": self.finished_at}


class BoUpdater:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.job: BoJob | None = None
        self._cleaner: Cleaner | None = None  # built once from the pack's vocabulary (it takes some seconds)
        self._lock = threading.Lock()

    # ---- control -----------------------------------------------------------------------------------------------
    def start(self, dry_run: bool = False) -> BoJob:
        with self._lock:
            if self.job and self.job.state in ("queued", "running"):
                raise RuntimeError("an update is already running")
            self.job = job = BoJob(dry_run)
        threading.Thread(target=self._run, args=(job,), daemon=True, name=f"bo-update-{job.id}").start()
        return job

    def cancel(self) -> bool:
        if self.job and self.job.state in ("queued", "running"):
            self.job.cancel.set()
            return True
        return False

    def problems(self) -> list[str]:
        """Why an update cannot run right now (shown in the UI before the user clicks)."""
        c, s, out = self.ctx, self.ctx.settings, []
        if c.mode == "offline":
            out.append("The app is in offline mode: switch to hybrid mode to let it contact the SGG site.")
        import importlib.util

        missing = [pip for mod, pip in (("fontTools", "fonttools"), ("pdfplumber", "pdfplumber"), ("pikepdf", "pikepdf"), ("pypdfium2", "pypdfium2"))
                   if importlib.util.find_spec(mod) is None]
        if missing:  # checked before anything is downloaded: the PDF reader needs them
            out.append(f"Packages needed to read the Bulletin PDFs are missing. Install them:  pip install {' '.join(missing)}")
        if not (s.resolved_bo_pipeline_dir() / "extract_bo_pdf.py").exists():
            out.append(f"extract_bo_pdf.py was not found in {s.resolved_bo_pipeline_dir()} (the bundled scripts are missing).")
        if not c.pack:
            out.append("No law pack is loaded: build one first (legalrag-build).")
        elif not c.pack_usable():
            out.append(f"The law pack is not trusted: {c.pack_error}")
        else:
            emb = c.embedder()
            if emb is None or getattr(emb, "embedder_id", None) not in c.pack.embedders():
                out.append(f"The pack's vectors come from {sorted(c.pack.embedders())}, but this machine would embed with "
                           f"'{getattr(emb, 'embedder_id', None)}': set LEGALRAG_EMBEDDER_ID / LEGALRAG_EMBEDDER_LOCAL_KIND to match, or new text would never be found.")
            if c.pack_trust and c.pack_trust.state == "signed_valid":
                priv = local_private_key(s)
                if not priv:
                    out.append("The pack was signed with a key that is not on this machine, so the updated pack cannot be re-signed. Rebuild the pack once on this machine (legalrag-build build ...): the key is then made automatically.")
                elif public_from_private(priv) != effective_public_key(s):
                    out.append("The pack was signed with another key than this machine's: rebuild the pack once on this machine so the app can keep it up to date.")
        if self._pipeline_mode():
            for f in ("chunk_bo.py", "embed_chunks.py"):
                if not (s.resolved_bo_pipeline_dir() / f).exists():
                    out.append(f"The pack was built from pipeline chunks, so new issues are chunked/embedded with {f}: it was not found in {s.resolved_bo_pipeline_dir()}.")
        if not s.bo_url_template and not s.bo_listing_urls:
            out.append("Set LEGALRAG_BO_URL_TEMPLATE or LEGALRAG_BO_LISTING_URLS so the app knows where the SGG files are.")
        return out

    def status(self) -> dict:
        s = self.ctx.settings
        done, _known, pending = discover.issue_state(s.resolved_bo_dir(), self._pack_numbers())
        return {"problems": self.problems(), "newest_local": max([n for n, _ in done] or [0]) or None, "issues_local": len(done), "pending_local": len(pending),
                "last_bo_check": self.ctx.pack.meta.get("last_bo_check") if self.ctx.pack else None, "job": self.job.to_dict() if self.job else None}

    def _pipeline_mode(self) -> bool:
        p = self.ctx.pack
        try:
            return bool(p and p.meta.get("chunk_source") == "pipeline")
        except Exception:
            return False

    def _pack_embedder_model(self, embedder_id: str) -> str | None:
        try:
            rows = self.ctx.pack._q("SELECT model FROM embedder WHERE embedder_id=?", (embedder_id,))
            return rows[0]["model"] if rows else None
        except Exception:
            return None

    def _chunk_and_embed(self, job: BoJob, st: dict, mds: list[Path]):
        """Run the pipeline's own chunk_bo.py and embed_chunks.py on the new .md files, then read their output (nothing is embedded by the backend)."""
        s, pdir = self.ctx.settings, self.ctx.settings.resolved_bo_pipeline_dir()
        emb = self.ctx.embedder()
        model = self._pack_embedder_model(emb.embedder_id) or "BAAI/bge-m3"
        n = len(mds)
        st.update(total=n * 2)
        for i, md in enumerate(mds):
            self._check_cancel(job)
            st["detail"] = f"chunking {md.stem}"
            r = subprocess.run([sys.executable, str(pdir / "chunk_bo.py"), str(md), "--overwrite", *s.bo_chunk_args], capture_output=True, text=True,
                               timeout=s.bo_extract_timeout_s, cwd=str(pdir))
            if r.returncode != 0:
                raise RuntimeError(f"chunk_bo.py failed on {md.name}: {(r.stderr or r.stdout).strip().splitlines()[-1:]}")
            st["done"] = i + 1
        for i, md in enumerate(mds):
            self._check_cancel(job)
            st["detail"] = f"embedding {md.stem} ({model})"
            cmd = [sys.executable, str(pdir / "embed_chunks.py"), str(md.with_suffix(".chunks.jsonl")), "--model", model, *s.bo_embed_args]
            cmd += ["--model-dir", str(s.resolved_embed_model_dir(model))]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=s.bo_embed_timeout_s, cwd=str(pdir))
            if r.returncode != 0:
                raise RuntimeError(f"embed_chunks.py failed on {md.name}: {(r.stderr or r.stdout).strip().splitlines()[-1:]}")
            st["done"] = n + i + 1
        try:
            return load_pipeline_chunks(mds[0].parent, only=[m.with_suffix(".chunks.jsonl") for m in mds]).with_embedder_id(emb.embedder_id)
        except PipelineImportError as e:
            raise RuntimeError(str(e))

    def _pack_numbers(self) -> list[str]:
        if not self.ctx.pack:
            return []
        try:
            return [r["bo_number"] for r in self.ctx.pack._q("SELECT DISTINCT bo_number FROM instrument WHERE bo_number IS NOT NULL")]
        except Exception:
            return []

    # ---- the job -----------------------------------------------------------------------------------------------
    def _run(self, job: BoJob) -> None:
        job.state = "running"
        try:
            self._steps(job)
            job.state = "done"
        except Cancelled:
            job.state, job.error = "cancelled", "stopped by the user; nothing was installed"
        except Exception as e:  # noqa: BLE001
            job.state, job.error = "error", f"{e.__class__.__name__}: {e}"
            for s in job.steps:
                if s["status"] == "running":
                    s["status"] = "error"
        finally:
            job.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _clean_texts(self, job: BoJob, st: dict, mds: list[Path], root: Path) -> int:
        """Repairs words the PDF damaged (split by a space, a letter left alone, a backwards lam-alef) before the text is split and embedded.
        Only safe cases, decided with the vocabulary of the pack; the originals are kept in md_raw/ and every change is written to a report."""
        if not self.ctx.settings.bo_text_cleanup:
            return 0
        st["detail"] = "repairing damaged words"
        try:
            if self._cleaner is None:
                self._cleaner = Cleaner.from_pack(self.ctx.settings.resolved_lawpack_path())
        except Exception as e:  # noqa: BLE001 - never block an update for this
            job.warnings.append(f"word repair skipped ({e.__class__.__name__}: {e})")
            return 0
        if not self._cleaner.usable():
            return 0
        total, lines = 0, []
        for md in mds:
            ch = self._cleaner.clean_file(md, raw_dir=root / "md_raw")
            total += len(ch)
            if ch:
                lines.append(f"## {md.name}: {len(ch)} change(s)")
                lines += [f"- {c}" for c in ch]
        if total:
            rep = root / "repairs" / f"{datetime.now(timezone.utc):%Y%m%d_%H%M}.md"
            rep.parent.mkdir(parents=True, exist_ok=True)
            rep.write_text("\n".join(lines) + "\n", encoding="utf-8")
            job.log.append(f"{total} damaged word(s) repaired; list: {rep}")
        return total

    def _check_cancel(self, job: BoJob) -> None:
        if job.cancel.is_set():
            raise Cancelled()

    def _begin(self, job: BoJob, sid: str, total: int = 0, detail: str = "") -> dict:
        self._check_cancel(job)
        st = job.step(sid)
        st.update(status="running", done=0, total=total, detail=detail)
        return st

    def _steps(self, job: BoJob) -> None:
        ctx, s = self.ctx, self.ctx.settings
        bad = self.problems()
        if bad:
            raise RuntimeError(bad[0])
        root = s.resolved_bo_dir()
        pdf_dir, md_dir, frozen = root / "pdfs", root / "md", root / "frozen"
        for d in (pdf_dir, md_dir):
            d.mkdir(parents=True, exist_ok=True)

        # 1. check ------------------------------------------------------------------------------------------------------
        st = self._begin(job, "check", detail="contacting sgg.gov.ma")
        _done, have, pending = discover.issue_state(root, self._pack_numbers())
        cands = discover.discover(s, have, log=job.log.append)
        have_keys = {(c.number, c.bis) for c in cands}
        for c in pending:  # downloaded earlier, never installed: process them now
            if (c.number, c.bis) not in have_keys:
                cands.append(c)
                job.log.append(f"{c.name}: found in the folder from an earlier run, not installed yet")
        cands.sort(key=lambda c: (c.number, c.bis))
        job.found = [{"name": c.name, "number": c.number, "url": c.url} for c in cands]
        st.update(status="done", done=1, total=1, detail=f"{len(cands)} new issue(s)" if cands else "no new issue")
        if not cands or job.dry_run:
            for sid in ("download", "extract", "ingest", "install"):
                job.step(sid).update(status="skipped", detail="nothing to do" if not cands else "dry run")
            return

        # 2. download -----------------------------------------------------------------------------------------------------
        st = self._begin(job, "download", total=len(cands))
        pdfs: list[tuple[discover.Candidate, Path, str]] = []
        for i, c in enumerate(cands):
            self._check_cancel(job)
            st["detail"] = c.name
            try:
                p, sha = discover.download(c, pdf_dir, s.bo_max_pdf_mb, s.bo_download_timeout_s)
                pdfs.append((c, p, sha))
            except Exception as e:  # noqa: BLE001
                job.warnings.append(f"{c.name}: download failed ({e.__class__.__name__}: {e})")
            st["done"] = i + 1
        st.update(status="done", detail=f"{len(pdfs)} of {len(cands)} downloaded")
        if not pdfs:
            raise RuntimeError("no file could be downloaded")

        # 3. extract (your extract_bo_pdf.py, run as it is) ----------------------------------------------------------------------
        st = self._begin(job, "extract", total=len(pdfs))
        mds: list[Path] = []
        script = s.resolved_bo_pipeline_dir() / "extract_bo_pdf.py"
        for i, (c, pdf, _sha) in enumerate(pdfs):
            self._check_cancel(job)
            st["detail"] = c.name
            out_prefix = md_dir / c.name
            r = subprocess.run([sys.executable, str(script), str(pdf), "-o", str(out_prefix), "-j", "1"], capture_output=True, text=True, timeout=s.bo_extract_timeout_s,
                               cwd=str(script.parent))
            md = Path(f"{out_prefix}.md")
            if r.returncode != 0 or not md.exists():
                job.warnings.append(f"{c.name}: extraction failed: {(r.stderr or '').strip().splitlines()[-1:] or ['unknown error']}")
            else:
                mds.append(md)
                err = r.stderr or ""
                m = re.search(r"(\d+) left as U\+FFFD", err)
                if m and int(m.group(1)):
                    job.warnings.append(f"{c.name}: {m.group(1)} unreadable letter(s) left (a font the extractor does not know yet)")
                m = re.search(r"scanned/image-only pages[^\[]*\[([^\]]*)\]", err)
                if m:
                    job.warnings.append(f"{c.name}: scanned pages without text: {m.group(1)[:80]}")
            st["done"] = i + 1
        if not mds:
            st.update(status="error", detail=f"0 of {len(pdfs)} read")
            raise RuntimeError("no PDF could be read")
        fixed = self._clean_texts(job, st, mds, root)
        st.update(status="done", detail=f"{len(mds)} of {len(pdfs)} read" + (f", {fixed} damaged word(s) repaired" if fixed else ""))

        # 4. parse (+ chunk and embed with the pipeline's scripts when the pack came from them) -----------------------------------------------------
        st = self._begin(job, "ingest", total=1, detail="splitting into articles")
        pipe = None
        if self._pipeline_mode():
            pipe = self._chunk_and_embed(job, st, mds)
        fr = freeze_pdfs(pdf_dir, frozen)
        src, rep = bo_to_sources(mds, pdf_dir, frozen, md_dir)
        for sk in rep["skipped"][:20]:
            job.warnings.append(f"{sk.get('file')}: skipped a block ({sk.get('reason')})")
        chk = checks.Report()
        checks.check_sources(dict(src, provisions=src["provisions"]), chk)
        issue_keys = [k for k in (discover.parse_name(m.name) for m in mds) if k]
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if not src["provisions"]:  # a bulletin with no legal text (reports, notices): finished, not "new" again at the next check
            job.warnings.append("no legal article could be read from: " + ", ".join(m.name for m in mds) + " (they probably hold no legal text)")
            discover.mark_done(root, issue_keys, 0, now)
            st.update(status="done", done=1, total=1, detail="no legal article in the new issue(s)")
            job.added = {"issues": len(mds), "instruments": 0, "articles": 0, "chunks": 0, "edges": 0, "already_in_pack": 0, "pack_version": None}
            job.step("install").update(status="skipped", detail="nothing new to add")
            return
        dest = s.resolved_lawpack_path()
        work = dest.with_name("update-work.db")
        shutil.copy2(dest, work)
        for sfx in (".sig",):
            work.with_suffix(".db" + sfx).unlink(missing_ok=True)
        version = f"{datetime.now(timezone.utc):%Y.%m.%d.%H%M}-bo"

        def prog(_k: str, done: int, total: int) -> None:
            self._check_cancel(job)
            st.update(done=done, total=total, detail=(f"storing {done}/{total} passages" if pipe is not None else f"embedding {done}/{total} passages"))

        signing_key = local_private_key(s) if (ctx.pack_trust and ctx.pack_trust.state == "signed_valid") else None
        try:
            res = append_sources(work, src, ctx.embedder(), version, signing_key, progress=prog, pipeline=pipe)
        except AppendError as e:
            raise RuntimeError(str(e))
        pr = res.get("pipeline")
        if pr:
            if pr["unmatched_chunks"]:
                job.warnings.append(f"{pr['unmatched_chunks']} chunk(s) could not be matched to an article and were left out: {pr['unmatched_text'][:3]}")
            if pr["provisions_without_chunk"]:
                job.warnings.append(f"{pr['provisions_without_chunk']} article(s) have no chunk (not searchable by meaning)")
        st.update(status="done", done=st["total"], detail=f"{res['articles']} articles, {res['chunks']} passages")
        job.added = {"issues": len(mds), "instruments": res["instruments"], "articles": res["articles"], "chunks": res["chunks"], "edges": res["edges"],
                     "already_in_pack": res["skipped_existing"], "pack_version": version}
        if not res["articles"]:
            discover.mark_done(root, issue_keys, 0, now)
            for sid in ("install",):
                job.step(sid).update(status="skipped", detail="nothing new to add")
            work.unlink(missing_ok=True)
            return

        # 5. install (verify + replace in one step) --------------------------------------------------------------------------------
        st = self._begin(job, "install", total=1)
        self._check_cancel(job)
        try:
            install_pack(ctx, work, work.with_suffix(".db.sig") if work.with_suffix(".db.sig").exists() else None)
        except PackError as e:
            raise RuntimeError(f"the updated pack was refused: {e}")
        finally:
            work.unlink(missing_ok=True)
            work.with_suffix(".db.sig").unlink(missing_ok=True)
        discover.mark_done(root, issue_keys, res["articles"], now)  # only after the pack is really installed
        st.update(status="done", done=1, detail=f"pack {version}")
