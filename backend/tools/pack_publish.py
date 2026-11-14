"""Prepare your law pack for a GitHub Release (run by YOU, the publisher).

    py tools\pack_publish.py --tag pack-2026.11.13

What it does: copies your current pack (current.db) and its signature (current.db.sig) into the folder  release_out\ , prints the size, the SHA-256 and
YOUR public key, and writes  pack_release.json  (commit that file: it tells users where to download and which key to trust).
Then you upload the two files in release_out\ to a GitHub Release with that tag (website: Releases > Draft a new release > attach both files)."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from legalrag.config import Settings  # noqa: E402
from legalrag.store.lawpack import LawPack  # noqa: E402
from legalrag.store.localkey import effective_public_key  # noqa: E402
from legalrag.store.signing import sha256_file, verify_pack  # noqa: E402

OUT = Path("release_out")
RELEASE = Path("pack_release.json")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True, help="the Release tag you will create on GitHub, e.g. pack-2026.11.13")
    ap.add_argument("--repo", default="YOUR-NAME/YOUR-REPO", help="owner/repo of the GitHub repository (or of the Hugging Face dataset with --host hf)")
    ap.add_argument("--host", choices=["github", "hf"], default="github", help="github = a Release file (limit 2 GB); hf = a Hugging Face dataset repo (no 2 GB limit, free)")
    a = ap.parse_args()
    s = Settings()
    db = s.resolved_lawpack_path()
    if not db.exists():
        print(f"no pack at {db}")
        return 1
    sig = db.with_suffix(db.suffix + ".sig")
    pub = effective_public_key(s)
    trust = verify_pack(db, pub, sig)
    if trust.state != "signed_valid" or not pub:
        print(f"the pack on this machine is not validly signed ({trust.state} {trust.detail}): rebuild or update it first")
        return 1
    pk = LawPack(db)
    version = pk.version
    pk.close()
    OUT.mkdir(exist_ok=True)
    shutil.copy2(db, OUT / "current.db")
    shutil.copy2(sig, OUT / "current.db.sig")
    base = f"https://github.com/{a.repo}/releases/download/{a.tag}" if a.host == "github" else f"https://huggingface.co/datasets/{a.repo}/resolve/main"
    info = {"pack_version": version, "sha256": sha256_file(db), "size_bytes": db.stat().st_size, "public_key_hex": pub,
            "db_url": f"{base}/current.db", "sig_url": f"{base}/current.db.sig"}
    RELEASE.write_text(json.dumps(info, indent=2), encoding="utf-8")
    mb = info["size_bytes"] / 1e6
    too_big = a.host == "github" and info["size_bytes"] >= 2 * 1024**3 - 1024**2
    print(f"pack version : {version}\nsize         : {mb:,.0f} MB  ({info['size_bytes']:,} bytes)")
    if too_big:
        print("TOO BIG for a GitHub Release (limit: under 2 GiB = 2,147,483,648 bytes). Use --host hf (Hugging Face).")
    print(f"sha256       : {info['sha256']}\npublic key   : {pub}\n\nfiles ready in {OUT.resolve()}:\n  current.db\n  current.db.sig\nwritten: {RELEASE.resolve()}  (commit this file)")
    if a.repo.startswith("YOUR-"):
        print("\nNOTE: edit the two URLs in pack_release.json (or rerun with --repo owner/repo) once you know your repository name.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
