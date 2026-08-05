"""Integration tests for POST /onboarding/placement.

With DEBRIEF_ENGINE=fake (conftest), the analyzer estimates B1, so a placement
with spoken answers sets the level to B1 and pre-fills the profile.
"""

import pytest


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
