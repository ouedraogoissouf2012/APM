import pytest


@pytest.mark.asyncio
async def test_register_returns_token_and_user(client):
    resp = await client.post(
        "/auth/register",
        json={"email": "a@b.com", "password": "s3cret!", "native_language": "fr"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "a@b.com"
    assert body["user"]["cefr_level"] == "A1"


@pytest.mark.asyncio
async def test_register_duplicate_email_rejected(client):
    payload = {"email": "dup@b.com", "password": "s3cret!"}
    first = await client.post("/auth/register", json=payload)
    assert first.status_code == 201
    second = await client.post("/auth/register", json=payload)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_login_succeeds_with_correct_password(client):
    await client.post("/auth/register", json={"email": "log@b.com", "password": "s3cret!"})
    resp = await client.post("/auth/login", json={"email": "log@b.com", "password": "s3cret!"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]


@pytest.mark.asyncio
async def test_login_fails_with_wrong_password(client):
    await client.post("/auth/register", json={"email": "log2@b.com", "password": "s3cret!"})
    resp = await client.post("/auth/login", json={"email": "log2@b.com", "password": "nope"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_current_user(client):
    reg = await client.post("/auth/register", json={"email": "me@b.com", "password": "s3cret!"})
    token = reg.json()["access_token"]
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == "me@b.com"


@pytest.mark.asyncio
async def test_me_rejects_missing_token(client):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401
