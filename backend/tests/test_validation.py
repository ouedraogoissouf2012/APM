"""Integration tests for input validation (HTTP 422) and small API edge cases."""

import pytest


async def _auth_header(client, email):
    reg = await client.post("/auth/register", json={"email": email, "password": "s3cret!"})
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


@pytest.mark.asyncio
async def test_register_invalid_email_rejected(client):
    resp = await client.post(
        "/auth/register", json={"email": "not-an-email", "password": "s3cret!"}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_short_password_rejected(client):
    resp = await client.post("/auth/register", json={"email": "v@b.com", "password": "123"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_session_start_invalid_mode_rejected(client):
    headers = await _auth_header(client, "v2@b.com")
    resp = await client.post("/sessions/start", headers=headers, json={"mode": "karaoke"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_profile_update_with_empty_body_keeps_defaults(client):
    headers = await _auth_header(client, "v3@b.com")
    resp = await client.put("/me/profile", headers=headers, json={})
    assert resp.status_code == 200
    assert resp.json()["accent"] == "us"
    assert resp.json()["correction_intensity"] == "gentle"
