import pytest

from app.core.rate_limit import InMemoryRateLimiter
from app.features.auth.dependencies import get_login_rate_limiter
from app.main import app


@pytest.mark.asyncio
async def test_register_returns_tokens_and_user(client):
    resp = await client.post(
        "/auth/register",
        json={"email": "a@b.com", "password": "s3cret!", "native_language": "fr"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
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
    assert resp.json()["refresh_token"]


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


@pytest.mark.asyncio
async def test_refresh_rotates_token_and_old_one_is_rejected(client):
    reg = await client.post("/auth/register", json={"email": "r@b.com", "password": "s3cret!"})
    old_refresh = reg.json()["refresh_token"]

    refreshed = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["refresh_token"] != old_refresh

    reused = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert reused.status_code == 401  # rotated -> old token revoked


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(client):
    reg = await client.post("/auth/register", json={"email": "lo@b.com", "password": "s3cret!"})
    refresh = reg.json()["refresh_token"]

    out = await client.post("/auth/logout", json={"refresh_token": refresh})
    assert out.status_code == 204

    after = await client.post("/auth/refresh", json={"refresh_token": refresh})
    assert after.status_code == 401


@pytest.mark.asyncio
async def test_login_is_rate_limited(client):
    # Override the no-op limiter (set in conftest) with a real low-limit one.
    # Must reuse the SAME instance across requests so its state accumulates.
    limiter = InMemoryRateLimiter(max_hits=2, window_seconds=60)
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    await client.post("/auth/register", json={"email": "rl@b.com", "password": "s3cret!"})
    creds = {"email": "rl@b.com", "password": "s3cret!"}

    assert (await client.post("/auth/login", json=creds)).status_code == 200
    assert (await client.post("/auth/login", json=creds)).status_code == 200
    blocked = await client.post("/auth/login", json=creds)
    assert blocked.status_code == 429  # too many attempts
