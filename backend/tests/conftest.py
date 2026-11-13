from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from legalrag.builder.build import build_pack
from legalrag.builder.fixtures import fixture_sources
from legalrag.config import Settings
from legalrag.main import create_app
from legalrag.retrieval.embedders import HashingEmbedder
from legalrag.state import build_context
from legalrag.store.signing import generate_keypair

TODAY = date(2026, 10, 27)
TOKEN = "test-token"
H = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(scope="session")
def keys():
    return generate_keypair()


@pytest.fixture(scope="session")
def pack_path(tmp_path_factory, keys):
    out = tmp_path_factory.mktemp("pack") / "current.db"
    res = build_pack(fixture_sources(), out, [HashingEmbedder()], "fixture-test", keys[0], built_at="2026-10-20T00:00:00+00:00")
    assert res.stats["built"], res.report.to_dict()
    return out


@pytest.fixture()
def ctx(tmp_path, pack_path, keys):
    s = Settings(data_dir=tmp_path / "data", lawpack_path=pack_path, lawpack_public_key_hex=keys[1], api_token=TOKEN, ner_enabled=False, query_rewrite=False)
    c = build_context(s)
    c.today_fn = lambda: TODAY
    assert c.pack_usable(), c.pack_error
    yield c
    c.close()


@pytest.fixture()
def client(ctx):
    return TestClient(create_app(ctx.settings, ctx))
