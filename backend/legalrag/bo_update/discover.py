"""Find and download new Bulletin Officiel issues from the SGG site (public official PDFs, one click by the user).

Two ways, both read-only GETs:
  1. listing pages (settings.bo_listing_urls): every link that looks like .../BO_<n>[-bis][_Ar].pdf is a candidate;
  2. probing: from the newest issue we already have, try the next numbers (plain and -bis) at settings.bo_url_template.
A candidate counts only when the server really answers with a PDF (`%PDF` header).  Nothing is guessed about the content."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlparse

import httpx

BO_NAME = re.compile(r"BO_(\d{3,5})(-bis\d*)?_Ar\.pdf", re.I)
UA = {"User-Agent": "legalrag-local/0.1 (personal research tool; one request at a time)"}


@dataclass
class Candidate:
    name: str  # BO_7498_Ar
    number: int
    bis: str
    url: str

    @property
    def key(self) -> str:
        return f"{self.number}{self.bis}"


def parse_name(name: str) -> tuple[int, str] | None:
    m = BO_NAME.search(name)
    return (int(m.group(1)), (m.group(2) or "").lower()) if m else None


def local_issues(*folders: Path, pack_numbers: list[str] | None = None) -> set[tuple[int, str]]:
    """Issues we already have: any BO_<n>_Ar file name (pdf or md) under the folders, plus the numbers recorded in the pack."""
    have: set[tuple[int, str]] = set()
    for f in folders:
        if f and f.exists():
            for p in f.rglob("*"):
                if p.suffix.lower() in (".pdf", ".md"):
                    k = parse_name(p.name)
                    if k:
                        have.add(k)
    for n in pack_numbers or []:
        m = re.fullmatch(r"(\d+)(?:[\s_-]*(bis\d*))?", str(n).strip().lower())  # "7465", "7465 bis", "7465-bis2"
        if m:
            have.add((int(m.group(1)), f"-{m.group(2)}" if m.group(2) else ""))
    return have


STATE_FILE = "update_state.json"


def _key_str(k: tuple[int, str]) -> str:
    return f"{k[0]}{k[1]}"


def load_done(root: Path) -> set[tuple[int, str]]:
    """Issues the updater has FINISHED (articles added to the pack, or nothing legal in them).  A downloaded file alone is not "done"."""
    try:
        data = json.loads((Path(root) / STATE_FILE).read_text("utf-8"))
    except (OSError, ValueError):
        return set()
    out = set()
    for k in data.get("done", {}):
        m = re.fullmatch(r"(\d+)(-bis\d*)?", k)
        if m:
            out.add((int(m.group(1)), m.group(2) or ""))
    return out


def mark_done(root: Path, keys: list[tuple[int, str]], articles: int, when: str) -> None:
    f = Path(root) / STATE_FILE
    try:
        data = json.loads(f.read_text("utf-8"))
    except (OSError, ValueError):
        data = {}
    done = data.setdefault("done", {})
    for k in keys:
        done[_key_str(k)] = {"at": when, "articles": articles}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, indent=1, sort_keys=True), "utf-8")


def issue_state(root: Path, pack_numbers: list[str] | None = None) -> tuple[set[tuple[int, str]], set[tuple[int, str]], list["Candidate"]]:
    """-> (done, known, pending).
    done    = issues in the pack + issues the updater finished;
    known   = done + every older file in the folder (history that was never meant to be fetched again);
    pending = PDFs in <root>/pdfs NEWER than everything done: downloaded by an earlier run that stopped before they were installed.
              They are processed again (no new download) instead of being mistaken for "already have"."""
    root = Path(root)
    done = local_issues(pack_numbers=pack_numbers) | load_done(root)
    newest = max([n for n, _ in done] or [0])
    files = local_issues(root)
    known = done | {k for k in files if k[0] <= newest}
    pending = []
    pdf_dir = root / "pdfs"
    if pdf_dir.exists():
        for p in sorted(pdf_dir.rglob("*.pdf")):
            k = parse_name(p.name)
            if k and k not in done and k[0] > newest and not any(c.key == f"{k[0]}{k[1]}" for c in pending):
                pending.append(Candidate(f"BO_{k[0]}{k[1]}_Ar", k[0], k[1], ""))
    return done, known, pending


def _is_pdf_response(r: httpx.Response) -> bool:
    return r.status_code == 200 and (r.content[:5] == b"%PDF-" if r.content else False)


def _from_listings(urls: list[str], client: httpx.Client, log: Callable[[str], None]) -> list[Candidate]:
    out: dict[str, Candidate] = {}
    for u in urls:
        try:
            r = client.get(u)
            r.raise_for_status()
        except httpx.HTTPError as e:
            log(f"listing {urlparse(u).netloc} unreachable: {e.__class__.__name__}")
            continue
        for href in re.findall(r"""href\s*=\s*["']([^"']+\.pdf[^"']*)["']""", r.text, re.I):
            k = parse_name(href)
            if k:
                num, bis = k
                url = urljoin(u, href)
                out.setdefault(f"{num}{bis}", Candidate(f"BO_{num}{bis}_Ar", num, bis, url))
    return list(out.values())


def _probe(template: str, start: int, ahead: int, have: set[tuple[int, str]], client: httpx.Client, log: Callable[[str], None],
           today: date | None = None) -> list[Candidate]:
    today = today or date.today()
    years = [today.year, today.year - 1]
    found: list[Candidate] = []
    misses = 0
    for num in range(start + 1, start + 1 + ahead):
        hit = False
        for bis in ("", "-bis", "-bis2"):
            if (num, bis) in have:
                hit = True
                continue
            for y in years:
                url = template.format(year=y, num=f"{num}{bis}")
                try:
                    with client.stream("GET", url) as r:
                        head = b""
                        if r.status_code == 200:
                            for chunk in r.iter_bytes(8):
                                head = chunk
                                break
                        ok = r.status_code == 200 and head[:5] == b"%PDF-"
                except httpx.HTTPError:
                    ok = False
                if ok:
                    found.append(Candidate(f"BO_{num}{bis}_Ar", num, bis, url))
                    hit = True
                    break
        misses = 0 if hit else misses + 1
        if misses >= 3:  # three numbers in a row with nothing: we are past the newest issue
            break
    log(f"probed up to BO {num}: {len(found)} new")
    return found


def discover(settings, have: set[tuple[int, str]], log: Callable[[str], None] = lambda s: None, client: httpx.Client | None = None) -> list[Candidate]:
    client = client or httpx.Client(timeout=30, follow_redirects=True, headers=UA)
    cands: dict[tuple[int, str], Candidate] = {}
    for c in _from_listings(settings.bo_listing_urls, client, log):
        if (c.number, c.bis) not in have:
            cands[(c.number, c.bis)] = c
    if settings.bo_url_template:
        newest = max([n for n, _ in have] or [0])
        if newest:
            seen = {(c.number, c.bis) for c in cands.values()}
            for c in _probe(settings.bo_url_template, newest, settings.bo_probe_ahead, have | seen, client, log):
                cands.setdefault((c.number, c.bis), c)
    return sorted(cands.values(), key=lambda c: (c.number, c.bis))


def download(c: Candidate, dest_dir: Path, max_mb: int, timeout: float, progress: Callable[[int, int | None], None] | None = None,
             client: httpx.Client | None = None) -> tuple[Path, str]:
    """-> (pdf path, sha256).  Written to a .part file first; only a complete file with a PDF header is kept."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"{c.name}.pdf"
    if out.exists():  # a complete file from an earlier run: use it, do not fetch it again
        data = out.read_bytes()
        if data.startswith(b"%PDF-") and len(data) > 1000:
            return out, hashlib.sha256(data).hexdigest()
    if not c.url:
        raise ValueError("the local file is not a valid PDF and there is no address to fetch it again")
    part = out.with_suffix(".part")
    client = client or httpx.Client(timeout=timeout, follow_redirects=True, headers=UA)
    h = hashlib.sha256()
    done = 0
    with client.stream("GET", c.url) as r:
        r.raise_for_status()
        total = int(r.headers["content-length"]) if r.headers.get("content-length", "").isdigit() else None
        with part.open("wb") as f:
            for block in r.iter_bytes(1 << 16):
                if done == 0 and not block.startswith(b"%PDF-"):
                    part.unlink(missing_ok=True)
                    raise ValueError("the server did not return a PDF")
                done += len(block)
                if done > max_mb << 20:
                    part.unlink(missing_ok=True)
                    raise ValueError(f"file larger than {max_mb} MB: refused")
                h.update(block)
                f.write(block)
                if progress:
                    progress(done, total)
    if total is not None and done != total:
        part.unlink(missing_ok=True)
        raise ValueError(f"incomplete download ({done} of {total} bytes)")
    part.replace(out)
    return out, h.hexdigest()
