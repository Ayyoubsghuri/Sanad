"""Download and install the law pack (run by USERS who cloned the repository).

    py tools\install_pack.py                 # uses pack_release.json from the repository
    py tools\install_pack.py --db current.db --sig current.db.sig --key <public key hex>     # files you already downloaded

It checks the SHA-256 and the publisher's signature BEFORE anything is replaced, keeps the old pack as previous.db, then installs the new one in
the app's data folder (~\.moroccan-legal-rag\lawpack).  Restart the backend afterwards."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from legalrag.config import Settings  # noqa: E402
from legalrag.store.lawpack import LawPack  # noqa: E402
from legalrag.store.signing import sha256_file, verify_pack  # noqa: E402


def fetch(url: str, dest: Path, tries: int = 8) -> None:
    """Download with resume: a 2 GB file on a weak connection will break, so the part already received is kept and continued."""
    import time
    import urllib.error
    if not (url.startswith("https://") or url.startswith("http://127.0.0.1")):  # plain http only for a test on this machine
        raise SystemExit(f"refusing a non-https address: {url}")
    print(f"downloading {url}")
    for attempt in range(1, tries + 1):
        have = dest.stat().st_size if dest.exists() else 0
        req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
        try:
            with urllib.request.urlopen(req) as r:  # noqa: S310 - https only, checked above
                if have and r.status != 206:  # the server ignored the range: start again
                    have = 0
                    dest.unlink(missing_ok=True)
                total = have + int(r.headers.get("Content-Length") or 0)
                with open(dest, "ab" if have else "wb") as f:
                    while chunk := r.read(1 << 20):
                        f.write(chunk)
                        have += len(chunk)
                        if total:
                            print(f"\r  {have / 1e6:,.0f} / {total / 1e6:,.0f} MB", end="", flush=True)
            print()
            return
        except urllib.error.HTTPError as e:
            if e.code == 416:  # already complete
                print()
                return
            print(f"\n  error {e.code}, try {attempt}/{tries}")
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            print(f"\n  connection lost ({e}); try {attempt}/{tries}, continuing where it stopped")
        time.sleep(min(30, 2 * attempt))
    raise SystemExit("download failed: run the command again, it continues from the part already received")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", default="pack_release.json")
    ap.add_argument("--db")
    ap.add_argument("--sig")
    ap.add_argument("--key", help="the publisher's public key (hex); default: the one in pack_release.json")
    a = ap.parse_args()
    info = {}
    if Path(a.release).exists():
        info = json.loads(Path(a.release).read_text(encoding="utf-8"))
    key = a.key or info.get("public_key_hex")
    if not key:
        print("no publisher key: give --key or keep pack_release.json")
        return 1
    tmp = Settings().data_dir / "download"
    tmp.mkdir(parents=True, exist_ok=True)  # kept between runs so an interrupted download can continue
    try:
        if a.db:
            db, sig = Path(a.db), Path(a.sig or a.db + ".sig")
        else:
            if not info.get("db_url") or "YOUR-" in info["db_url"]:
                print("pack_release.json has no real download address yet (the publisher has not filled it in)")
                return 1
            db, sig = tmp / "current.db", tmp / "current.db.sig"
            for attempt in (1, 2):
                fetch(info["db_url"], db)
                sig.unlink(missing_ok=True)
                fetch(info["sig_url"], sig)
                if not info.get("sha256") or sha256_file(db) == info["sha256"]:
                    break
                db.unlink(missing_ok=True)  # an older or damaged part from an earlier run: start the download again
                if attempt == 2:
                    print("the download does not match the published SHA-256: not installed")
                    return 1
        trust = verify_pack(db, key, sig)
        if trust.state != "signed_valid":
            print(f"REJECTED ({trust.state}): {trust.detail}\nnothing was changed")
            return 1
        LawPack(db).close()  # opens it and reads the meta: catches a corrupted file
        dest = Settings().resolved_lawpack_path()
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.copy2(dest, dest.with_name("previous.db"))
        (shutil.move if db.parent == tmp else shutil.copy2)(str(db), str(dest))  # a downloaded 2 GB file is moved, not copied twice
        shutil.copy2(sig, dest.with_suffix(dest.suffix + ".sig"))
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"installed: {dest}\nNow set the publisher key for the backend and restart it:\n  setx LEGALRAG_LAWPACK_PUBLIC_KEY_HEX {key}")
        return 0
    except KeyboardInterrupt:
        print("\nstopped: run the command again to continue the download")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
