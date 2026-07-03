import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.middleware import RequestContextMiddleware


def _middleware_app(*, enable_hsts: bool) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware, enable_hsts=enable_hsts)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


async def _get_health(*, enable_hsts: bool, base_url: str = "http://test", headers=None):
    transport = ASGITransport(app=_middleware_app(enable_hsts=enable_hsts))
    async with AsyncClient(transport=transport, base_url=base_url) as ac:
        return await ac.get("/health", headers=headers)


@pytest.mark.asyncio
async def test_response_has_request_id_and_security_headers(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("Referrer-Policy") == "no-referrer"
    assert "default-src 'none'" in resp.headers.get("Content-Security-Policy", "")
    assert "camera=()" in resp.headers.get("Permissions-Policy", "")


@pytest.mark.asyncio
async def test_incoming_request_id_is_echoed(client):
    resp = await client.get("/health", headers={"X-Request-ID": "abc123"})
    assert resp.headers.get("X-Request-ID") == "abc123"


@pytest.mark.asyncio
async def test_security_headers_on_health_without_database():
    resp = await _get_health(enable_hsts=False)

    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("Referrer-Policy") == "no-referrer"
    assert "default-src 'none'" in resp.headers.get("Content-Security-Policy", "")
    assert "microphone=()" in resp.headers.get("Permissions-Policy", "")


@pytest.mark.asyncio
async def test_hsts_absent_in_dev():
    resp = await _get_health(enable_hsts=False, base_url="https://test")

    assert "Strict-Transport-Security" not in resp.headers


@pytest.mark.asyncio
async def test_hsts_present_in_production_https():
    resp = await _get_health(enable_hsts=True, base_url="https://test")

    assert resp.headers.get("Strict-Transport-Security") == (
        "max-age=63072000; includeSubDomains; preload"
    )


@pytest.mark.asyncio
async def test_hsts_present_in_production_behind_https_proxy():
    resp = await _get_health(enable_hsts=True, headers={"X-Forwarded-Proto": "https"})

    assert resp.headers.get("Strict-Transport-Security") == (
        "max-age=63072000; includeSubDomains; preload"
    )


@pytest.mark.asyncio
async def test_request_id_echo_without_database():
    resp = await _get_health(enable_hsts=False, headers={"X-Request-ID": "abc123"})

    assert resp.headers.get("X-Request-ID") == "abc123"


@pytest.mark.asyncio
async def test_cors_headers_present_for_cross_origin_request(client):
    resp = await client.get("/health", headers={"Origin": "http://example.com"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") in ("http://example.com", "*")
