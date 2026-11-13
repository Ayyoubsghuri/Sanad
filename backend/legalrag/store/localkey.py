"""The pack-signing key of THIS machine, made and kept automatically (OS keychain / encrypted file via KeyStore).

Nobody has to generate, copy or export a key: the first build or update creates it, the same machine signs, and the app trusts its public
half.  A key set by hand (LEGALRAG_LAWPACK_PUBLIC_KEY_HEX / LEGALRAG_PACK_PRIVATE_KEY_HEX) always wins, so a pack signed elsewhere is still
checked against its publisher's key."""
from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from .crypto import KeyStore
from .signing import generate_keypair

SECRET = "pack_signing_key"


def public_from_private(private_hex: str) -> str:
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_hex)).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


def local_private_key(settings, create: bool = False) -> str | None:
    """The configured private key, else this machine's own (made on first use when create=True)."""
    if settings.pack_private_key_hex:
        return settings.pack_private_key_hex
    ks = KeyStore(settings.data_dir)
    k = ks.get_secret(SECRET)
    if not k and create:
        k, _pub = generate_keypair()
        ks.set_secret(SECRET, k)
    return k


def effective_public_key(settings) -> str | None:
    """The key that must have signed the pack: the configured one, else this machine's own (if it has one)."""
    if settings.lawpack_public_key_hex:
        return settings.lawpack_public_key_hex
    k = local_private_key(settings)
    return public_from_private(k) if k else None
