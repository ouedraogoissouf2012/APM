import pytest


async def _auth_header(client):
    reg = await client.post("/auth/register", json={"email": "p@b.com", "password": "s3cret!pass"})
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


@pytest.mark.asyncio
async def test_get_profile_returns_defaults(client):
    headers = await _auth_header(client)
    resp = await client.get("/me/profile", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["interests"] == []
    assert body["correction_intensity"] == "gentle"
    assert body["accent"] == "us"


@pytest.mark.asyncio
async def test_update_profile_persists(client):
    headers = await _auth_header(client)
    resp = await client.put(
        "/me/profile",
        headers=headers,
        json={"interests": ["football", "cinema"], "goal": "job interview", "accent": "uk"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["interests"] == ["football", "cinema"]
    assert body["goal"] == "job interview"
    assert body["accent"] == "uk"

    again = await client.get("/me/profile", headers=headers)
    assert again.json()["interests"] == ["football", "cinema"]
