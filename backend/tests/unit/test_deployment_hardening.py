"""Deployment hardening (#231): docs disabled in production only."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import _docs_enabled
from app.main import app as real_app


def test_docs_disabled_in_production():
    assert _docs_enabled("production") is False


def test_docs_enabled_in_dev():
    assert _docs_enabled("dev") is True


def test_docs_enabled_in_staging():
    # Staging is guarded by the JWT/CORS/keys validator (#231), but keeping docs
    # reachable there is intentional — it's where the API is built/tested against.
    assert _docs_enabled("staging") is True


def test_docs_enabled_in_test():
    assert _docs_enabled("test") is True


@pytest.mark.asyncio
async def test_the_real_app_serves_docs_outside_production():
    # Wiring check: the app instantiated at import time (app_env != production in
    # tests) must actually expose /docs, not just the pure function in isolation.
    transport = ASGITransport(app=real_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/docs")
    assert resp.status_code == 200
