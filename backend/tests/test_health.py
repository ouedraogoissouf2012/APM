import pytest


@pytest.mark.asyncio
async def test_health_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_config_reports_demo_mode_when_engine_is_fake(client):
    # The test suite forces VOICE_ENGINE/DEBRIEF_ENGINE=fake (see conftest),
    # so /config must advertise demo mode — the client shows a banner.
    resp = await client.get("/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["demo_mode"] is True
    assert body["debrief_demo_mode"] is True
