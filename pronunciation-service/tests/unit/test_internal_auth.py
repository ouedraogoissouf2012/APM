"""Shared-secret auth for /score (#231): the service has no other auth and used
to bind 0.0.0.0, so an unset secret must stay a no-op (dev/tests) while a
configured secret must reject a missing/wrong header."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from pronunciation.core.config import get_settings
from pronunciation.dependencies import require_internal_secret


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    # Settings is process-wide lru_cache'd; each test must see its own env change.
    yield
    get_settings.cache_clear()


def _guarded_app() -> FastAPI:
    app = FastAPI()

    @app.get("/guarded", dependencies=[Depends(require_internal_secret)])
    def guarded() -> dict[str, str]:
        return {"status": "ok"}

    return app


def test_unconfigured_secret_is_a_noop(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.delenv("INTERNAL_SECRET", raising=False)
    client = TestClient(_guarded_app())
    resp = client.get("/guarded")
    assert resp.status_code == 200


def test_configured_secret_rejects_missing_header(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("INTERNAL_SECRET", "s3cret-internal")
    client = TestClient(_guarded_app())
    resp = client.get("/guarded")
    assert resp.status_code == 401


def test_configured_secret_rejects_wrong_value(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("INTERNAL_SECRET", "s3cret-internal")
    client = TestClient(_guarded_app())
    resp = client.get("/guarded", headers={"X-Internal-Secret": "wrong"})
    assert resp.status_code == 401


def test_configured_secret_accepts_matching_header(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("INTERNAL_SECRET", "s3cret-internal")
    client = TestClient(_guarded_app())
    resp = client.get("/guarded", headers={"X-Internal-Secret": "s3cret-internal"})
    assert resp.status_code == 200
