"""Application-level encryption for the user database (vault, traces, drafts) and secret storage.

The master key lives in the OS keychain when one is available; otherwise in a 0600 file in the
data dir (reported by `key_storage` so the UI can warn). SQLite itself is not encrypted (no SQLCipher
dependency): every sensitive column is Fernet-encrypted before it is written.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet

SERVICE = "moroccan-legal-rag"


def _keyring():
    try:
        import keyring
        from keyring.errors import KeyringError  # noqa: F401

        kr = keyring.get_keyring()
        if kr.__class__.__module__.startswith("keyring.backends.fail") or kr.__class__.__name__ in {"Keyring", "NullKeyring"}:
            return None
        return keyring
    except Exception:
        return None


class KeyStore:
    """get/set small secrets in the OS keychain, falling back to an encrypted file."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        self._kr = _keyring()
        self.storage = "keychain" if self._kr else "file"
        self._master = self._load_master()
        self._fernet = Fernet(self._master)
        self._file = data_dir / "secrets.enc"

    # -- master key ------------------------------------------------------------------
    def _load_master(self) -> bytes:
        if self._kr:
            try:
                v = self._kr.get_password(SERVICE, "master-key")
                if not v:
                    v = Fernet.generate_key().decode()
                    self._kr.set_password(SERVICE, "master-key", v)
                return v.encode()
            except Exception:
                self._kr = None
                self.storage = "file"
        path = self.data_dir / "master.key"
        if path.exists():
            return path.read_bytes().strip()
        key = Fernet.generate_key()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(key)
        return key

    # -- encryption helpers -------------------------------------------------------------
    def encrypt(self, text: str) -> bytes:
        return self._fernet.encrypt(text.encode("utf-8"))

    def decrypt(self, blob: bytes | str) -> str:
        if isinstance(blob, str):
            blob = blob.encode()
        return self._fernet.decrypt(blob).decode("utf-8")

    def encrypt_json(self, obj) -> bytes:
        return self.encrypt(json.dumps(obj, ensure_ascii=False))

    def decrypt_json(self, blob):
        return json.loads(self.decrypt(blob))

    def blind_index(self, value: str) -> str:
        """Keyed hash so the vault can find an existing entity without decrypting every row."""
        k = hashlib.sha256(self._master + b"|blind-index").digest()
        return hmac.new(k, value.encode("utf-8"), hashlib.sha256).hexdigest()

    # -- named secrets (API keys) -----------------------------------------------------
    def _read_file(self) -> dict:
        if not self._file.exists():
            return {}
        try:
            return json.loads(self.decrypt(self._file.read_bytes()))
        except Exception:
            return {}

    def _write_file(self, data: dict) -> None:
        fd = os.open(self._file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(self.encrypt(json.dumps(data)))

    def get_secret(self, name: str) -> str | None:
        env = os.environ.get(f"LEGALRAG_SECRET_{name.upper()}")
        if env:
            return env
        if self._kr:
            try:
                return self._kr.get_password(SERVICE, f"secret:{name}")
            except Exception:
                pass
        return self._read_file().get(name)

    def set_secret(self, name: str, value: str) -> None:
        if self._kr:
            try:
                self._kr.set_password(SERVICE, f"secret:{name}", value)
                return
            except Exception:
                pass
        d = self._read_file()
        d[name] = value
        self._write_file(d)

    def delete_secret(self, name: str) -> None:
        if self._kr:
            try:
                self._kr.delete_password(SERVICE, f"secret:{name}")
            except Exception:
                pass
        d = self._read_file()
        if name in d:
            del d[name]
            self._write_file(d)

    def has_secret(self, name: str) -> bool:
        return bool(self.get_secret(name))


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode()
