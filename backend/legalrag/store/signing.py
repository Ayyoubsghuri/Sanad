"""Ed25519 signing / verification of law packs (tamper detection on every device)."""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

MAGIC = b"legalrag-pack-v1\n"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def generate_keypair() -> tuple[str, str]:
    """Returns (private_hex, public_hex). Keep the private key on the build machine only."""
    sk = Ed25519PrivateKey.generate()
    priv = sk.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()
    pub = sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    return priv, pub


def _message(sha: str, built_at: str, pack_version: str) -> bytes:
    return MAGIC + f"{sha}\n{built_at}\n{pack_version}".encode()


def sign_pack(db_path: Path, private_hex: str, built_at: str, pack_version: str) -> Path:
    sha = sha256_file(db_path)
    sk = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_hex))
    sig = sk.sign(_message(sha, built_at, pack_version))
    out = db_path.with_suffix(db_path.suffix + ".sig")
    out.write_text(
        json.dumps(
            {"alg": "ed25519", "sha256": sha, "size": db_path.stat().st_size, "built_at": built_at, "pack_version": pack_version, "signature": base64.b64encode(sig).decode()},
            indent=2,
        )
    )
    return out


@dataclass
class PackTrust:
    state: str  # signed_valid | unsigned | invalid | no_public_key
    detail: str = ""
    sha256: str | None = None

    @property
    def ok(self) -> bool:
        return self.state == "signed_valid"


def verify_pack(db_path: Path, public_hex: str | None, sig_path: Path | None = None) -> PackTrust:
    sig_path = sig_path or db_path.with_suffix(db_path.suffix + ".sig")
    sha = sha256_file(db_path)
    if not sig_path.exists():
        return PackTrust("unsigned", "no signature file next to the pack", sha)
    if not public_hex:
        return PackTrust("no_public_key", "no publisher public key configured", sha)
    try:
        meta = json.loads(sig_path.read_text())
        if meta.get("sha256") != sha:
            return PackTrust("invalid", "file hash does not match the signature (tampered or corrupted)", sha)
        pk = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_hex))
        pk.verify(base64.b64decode(meta["signature"]), _message(sha, meta["built_at"], meta["pack_version"]))
        return PackTrust("signed_valid", "", sha)
    except (InvalidSignature, KeyError, ValueError) as e:
        return PackTrust("invalid", f"signature check failed: {e.__class__.__name__}", sha)
