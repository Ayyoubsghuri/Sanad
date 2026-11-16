"""The in-app law pack update: check against the published description, download, verify, install."""
from __future__ import annotations

import time

import httpx
import pytest

from legalrag import pack_update
from legalrag.builder.build import build_pack
from legalrag.builder.fixtures import fixture_sources
from legalrag.config import Settings
from legalrag.retrieval.embedders import HashingEmbedder
from legalrag.state import build_context
from legalrag.store.signing import generate_keypair, sha256_file


@pytest.fixture()
def setup(tmp_path, keys):
    old = tmp_path / "installed" / "current.db"
    old.parent.mkdir()
    build_pack(fixture_sources(), old, [HashingEmbedder()], "2026.10.01.0900", keys[0], built_at="2026-10-01T09:00:00+00:00")
    new = tmp_path / "published.db"
    build_pack(fixture_sources(), new, [HashingEmbedder()], "2026.11.08.1455-retire", keys[0], built_at="2026-11-08T14:55:00+00:00")
    files = {"/current.db": new.read_bytes(), "/current.db.sig": new.with_suffix(".db.sig").read_bytes()}
    info = {"pack_version": "2026.11.08.1455-retire", "sha256": sha256_file(new), "size_bytes": new.stat().st_size,
            "public_key_hex": keys[1], "db_url": "https://example.test/current.db", "sig_url": "https://example.test/current.db.sig"}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/pack_release.json":
            return httpx.Response(200, json=info)
        data = files[req.url.path]
        rng = req.headers.get("range")
        if rng:
            start = int(rng.split("=")[1].split("-")[0])
            return httpx.Response(206, content=data[start:])
        return httpx.Response(200, content=data)

    real = httpx.Client
    pack_update.httpx.Client = lambda *a, **k: real(*a, **{**k, "transport": httpx.MockTransport(handler)})  # type: ignore[misc]
    s = Settings(data_dir=tmp_path / "data", lawpack_path=old, lawpack_public_key_hex=keys[1], ner_enabled=False, query_rewrite=False,
                 pack_release_url="https://example.test/pack_release.json")
    ctx = build_context(s)
    yield ctx, info
    pack_update.httpx.Client = real  # type: ignore[misc]
    ctx.close()


def _wait(u):
    for _ in range(200):
        if u.job["state"] not in ("queued", "running"):
            return u.job
        time.sleep(0.05)
    raise AssertionError(u.job)


def test_check_then_install(setup):
    ctx, info = setup
    u = pack_update.PackUpdater(ctx)
    c = u.check()
    assert c["installed_version"] == "2026.10.01.0900" and c["published_version"] == info["pack_version"]
    assert c["update_available"] and c["key_matches"]
    u.start()
    job = _wait(u)
    assert job["state"] == "done", job
    assert ctx.pack.version == info["pack_version"] and ctx.pack_usable()
    assert not (ctx.settings.resolved_lawpack_path().with_name("previous.db")).exists()   # one pack on disk
    assert u.check()["update_available"] is False


def test_other_publisher_key_is_refused(setup):
    ctx, info = setup
    info["public_key_hex"] = generate_keypair()[1]
    u = pack_update.PackUpdater(ctx)
    assert u.check()["key_matches"] is False
    u.start()
    job = _wait(u)
    assert job["state"] == "error" and "different key" in job["error"]
    assert ctx.pack and ctx.pack.version == "2026.10.01.0900"


def test_wrong_sha_is_refused(setup):
    ctx, info = setup
    info["sha256"] = "0" * 64
    u = pack_update.PackUpdater(ctx)
    u.start()
    job = _wait(u)
    assert job["state"] == "error" and "SHA-256" in job["error"]
    assert ctx.pack and ctx.pack.version == "2026.10.01.0900"


def test_local_bo_update_is_newer(setup):
    assert pack_update._stamp("2026.11.20.1010-bo") > pack_update._stamp("2026.11.08.1455-retire")
    assert pack_update._stamp("fixture-0") == ""
