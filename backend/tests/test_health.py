import pytest


@pytest.mark.asyncio
async def test_health_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_live_does_not_need_the_database(client):
    resp = await client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_ready_ok_without_redis(client):
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_metrics_starts_empty_and_counts_increments(client):
    from app.core import metrics

    metrics.reset()
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert resp.json() == {}
    metrics.inc(metrics.METER_FAILURES)
    assert (await client.get("/metrics")).json() == {"meter_failures": 1}
    metrics.reset()


@pytest.mark.asyncio
async def test_config_reports_demo_mode_when_engine_is_fake(client):
    # The test suite forces VOICE_ENGINE/DEBRIEF_ENGINE=fake (see conftest),
    # so /config must advertise demo mode — the client shows a banner.
    resp = await client.get("/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["demo_mode"] is True
    assert body["debrief_demo_mode"] is True
    assert body["password_reset_enabled"] is False
