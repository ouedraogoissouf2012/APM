import pytest


@pytest.mark.asyncio
async def test_response_has_request_id_and_security_headers(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"


@pytest.mark.asyncio
async def test_incoming_request_id_is_echoed(client):
    resp = await client.get("/health", headers={"X-Request-ID": "abc123"})
    assert resp.headers.get("X-Request-ID") == "abc123"


@pytest.mark.asyncio
async def test_cors_headers_present_for_cross_origin_request(client):
    resp = await client.get("/health", headers={"Origin": "http://example.com"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") in ("http://example.com", "*")
