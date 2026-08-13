"""Integration tests for POST /onboarding/placement.

With DEBRIEF_ENGINE=fake (conftest), the analyzer estimates B1, so a placement
with spoken answers sets the level to B1 and pre-fills the profile.
"""

import pytest

from app.core.rate_limit import InMemoryRateLimiter
from app.features.onboarding.dependencies import get_onboarding_rate_limiter
from app.main import app


async def _auth_header(client):
    reg = await client.post("/auth/register", json={"email": "o@b.com", "password": "s3cret!pass"})
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


@pytest.mark.asyncio
async def test_placement_sets_level_and_prefills_profile(client):
    headers = await _auth_header(client)

    resp = await client.post(
        "/onboarding/placement",
        headers=headers,
        json={
            "answers": ["I have been learning English for a few years now."],
            "interests": ["football", "travel"],
            "goal": "job interview",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["cefr_level"] == "B1"  # fake analyzer estimate
    assert body["interests"] == ["football", "travel"]
    assert body["goal"] == "job interview"

    # The estimated level is persisted on the account.
    me = await client.get("/auth/me", headers=headers)
    assert me.json()["cefr_level"] == "B1"

    # ...and the profile is pre-filled for the first real conversation.
    profile = await client.get("/me/profile", headers=headers)
    assert profile.json()["interests"] == ["football", "travel"]
    assert profile.json()["goal"] == "job interview"


@pytest.mark.asyncio
async def test_placement_without_answers_keeps_default_level(client):
    headers = await _auth_header(client)

    resp = await client.post(
        "/onboarding/placement",
        headers=headers,
        json={"answers": [], "interests": ["cooking"], "goal": "fun"},
    )
    assert resp.status_code == 200, resp.text
    # No spoken answer -> level stays at the A1 account default (skippable path).
    assert resp.json()["cefr_level"] == "A1"
    # But interests/goal the learner did provide are still saved.
    assert resp.json()["interests"] == ["cooking"]


@pytest.mark.asyncio
async def test_placement_requires_auth(client):
    resp = await client.post("/onboarding/placement", json={"answers": ["hi"]})
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_placement_rate_limit_is_not_bypassed_by_ip_rotation(client):
    """#356: the limiter key must be user_id-only. Before the fix, the IP was
    part of the key, so a free account rotating its apparent IP (VPN, or
    X-Forwarded-For under trust_proxy_headers) got a fresh bucket per IP on
    this paid (LLM-backed) endpoint — a denial-of-wallet."""
    headers = await _auth_header(client)
    limiter = InMemoryRateLimiter(max_hits=1, window_seconds=60)
    app.dependency_overrides[get_onboarding_rate_limiter] = lambda: limiter
    try:
        payload = {"answers": ["hi"], "interests": [], "goal": "g"}
        first = await client.post(
            "/onboarding/placement",
            headers={**headers, "X-Forwarded-For": "1.1.1.1"},
            json=payload,
        )
        assert first.status_code == 200, first.text
        second = await client.post(
            "/onboarding/placement",
            headers={**headers, "X-Forwarded-For": "2.2.2.2"},
            json=payload,
        )
        assert second.status_code == 429, second.text
    finally:
        app.dependency_overrides.pop(get_onboarding_rate_limiter, None)
