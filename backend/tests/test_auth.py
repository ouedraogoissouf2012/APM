import asyncio

import pytest

from app.core.rate_limit import InMemoryRateLimiter
from app.features.auth.dependencies import (
    get_change_password_rate_limiter,
    get_login_ip_rate_limiter,
    get_login_rate_limiter,
    get_refresh_rate_limiter,
    get_register_ip_rate_limiter,
    get_register_rate_limiter,
)
from app.main import app


@pytest.mark.asyncio
async def test_register_returns_tokens_and_user(client):
    resp = await client.post(
        "/auth/register",
        json={"email": "a@b.com", "password": "s3cret!pass", "native_language": "fr"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "a@b.com"
    assert body["user"]["cefr_level"] == "A1"


@pytest.mark.asyncio
async def test_register_rejects_oversized_native_language_with_normalized_422(client):
    """A native_language over its BCP-47 bound (max 8 chars) must be rejected by
    Pydantic before it ever reaches the database, with the SAME error envelope as
    every other error — not a bare {"detail": [...]} (#241)."""
    resp = await client.post(
        "/auth/register",
        json={
            "email": "toolong@b.com",
            "password": "s3cret!pass",
            "native_language": "way-too-long",
        },
    )
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message"}
    assert body["error"]["code"] == "ValidationError"


@pytest.mark.asyncio
async def test_register_duplicate_email_rejected(client):
    payload = {"email": "dup@b.com", "password": "s3cret!pass"}
    first = await client.post("/auth/register", json=payload)
    assert first.status_code == 201
    second = await client.post("/auth/register", json=payload)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_login_succeeds_with_correct_password(client):
    await client.post("/auth/register", json={"email": "log@b.com", "password": "s3cret!pass"})
    resp = await client.post("/auth/login", json={"email": "log@b.com", "password": "s3cret!pass"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]
    assert resp.json()["refresh_token"]


@pytest.mark.asyncio
async def test_login_fails_with_wrong_password(client):
    await client.post("/auth/register", json={"email": "log2@b.com", "password": "s3cret!pass"})
    resp = await client.post("/auth/login", json={"email": "log2@b.com", "password": "nope"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_current_user(client):
    reg = await client.post("/auth/register", json={"email": "me@b.com", "password": "s3cret!pass"})
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
    reg = await client.post("/auth/register", json={"email": "r@b.com", "password": "s3cret!pass"})
    old_refresh = reg.json()["refresh_token"]

    refreshed = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["refresh_token"] != old_refresh

    reused = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert reused.status_code == 401  # rotated -> old token revoked


@pytest.mark.asyncio
async def test_concurrent_refresh_allows_only_one_rotation(client):
    reg = await client.post(
        "/auth/register", json={"email": "race@b.com", "password": "s3cret!pass"}
    )
    refresh = reg.json()["refresh_token"]

    first, second = await asyncio.gather(
        client.post("/auth/refresh", json={"refresh_token": refresh}),
        client.post("/auth/refresh", json={"refresh_token": refresh}),
    )

    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [200, 401]
    success = first if first.status_code == 200 else second
    assert success.json()["refresh_token"] != refresh


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(client):
    reg = await client.post("/auth/register", json={"email": "lo@b.com", "password": "s3cret!pass"})
    refresh = reg.json()["refresh_token"]

    out = await client.post("/auth/logout", json={"refresh_token": refresh})
    assert out.status_code == 204

    after = await client.post("/auth/refresh", json={"refresh_token": refresh})
    assert after.status_code == 401


@pytest.mark.asyncio
async def test_register_is_rate_limited_by_ip_and_email(client):
    limiter = InMemoryRateLimiter(max_hits=1, window_seconds=60)
    app.dependency_overrides[get_register_rate_limiter] = lambda: limiter
    payload = {"email": "limited-register@b.com", "password": "s3cret!pass"}

    assert (await client.post("/auth/register", json=payload)).status_code == 201
    blocked = await client.post("/auth/register", json=payload)
    assert blocked.status_code == 429


@pytest.mark.asyncio
async def test_refresh_is_rate_limited(client):
    limiter = InMemoryRateLimiter(max_hits=1, window_seconds=60)
    app.dependency_overrides[get_refresh_rate_limiter] = lambda: limiter
    reg = await client.post(
        "/auth/register", json={"email": "limited-refresh@b.com", "password": "s3cret!pass"}
    )
    refresh = reg.json()["refresh_token"]

    assert (await client.post("/auth/refresh", json={"refresh_token": refresh})).status_code == 200
    blocked = await client.post("/auth/refresh", json={"refresh_token": refresh})
    assert blocked.status_code == 429


@pytest.mark.asyncio
async def test_login_is_rate_limited(client):
    # Override the no-op limiter (set in conftest) with a real low-limit one.
    # Must reuse the SAME instance across requests so its state accumulates.
    limiter = InMemoryRateLimiter(max_hits=2, window_seconds=60)
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    await client.post("/auth/register", json={"email": "rl@b.com", "password": "s3cret!pass"})
    creds = {"email": "rl@b.com", "password": "s3cret!pass"}

    assert (await client.post("/auth/login", json=creds)).status_code == 200
    assert (await client.post("/auth/login", json=creds)).status_code == 200
    blocked = await client.post("/auth/login", json=creds)
    assert blocked.status_code == 429  # too many attempts


@pytest.mark.asyncio
async def test_login_rate_limit_keys_are_independent_by_email(client):
    limiter = InMemoryRateLimiter(max_hits=1, window_seconds=60)
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    await client.post("/auth/register", json={"email": "one@b.com", "password": "s3cret!pass"})
    await client.post("/auth/register", json={"email": "two@b.com", "password": "s3cret!pass"})

    assert (
        await client.post("/auth/login", json={"email": "one@b.com", "password": "s3cret!pass"})
    ).status_code == 200
    assert (
        await client.post("/auth/login", json={"email": "two@b.com", "password": "s3cret!pass"})
    ).status_code == 200
    blocked = await client.post(
        "/auth/login", json={"email": "one@b.com", "password": "s3cret!pass"}
    )
    assert blocked.status_code == 429


@pytest.mark.asyncio
async def test_register_ip_rate_limit_blocks_across_different_emails_same_ip(client):
    # #355: the (ip, email) limiter alone is bypassed by varying the email on
    # every attempt — a fresh email always gets a fresh bucket there. This
    # second, IP-only limiter has no email component, so N distinct emails
    # from the same IP still hit one shared per-IP ceiling.
    limiter = InMemoryRateLimiter(max_hits=1, window_seconds=60)
    app.dependency_overrides[get_register_ip_rate_limiter] = lambda: limiter

    first = await client.post(
        "/auth/register", json={"email": "regipone@b.com", "password": "s3cret!pass"}
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        "/auth/register", json={"email": "regiptwo@b.com", "password": "s3cret!pass"}
    )
    assert second.status_code == 429, second.text


@pytest.mark.asyncio
async def test_login_ip_rate_limit_blocks_across_different_emails_same_ip(client):
    # #355: same bypass as register, closed the same way — an attacker rotating
    # the email on every login attempt from one IP must still hit a per-IP cap.
    limiter = InMemoryRateLimiter(max_hits=1, window_seconds=60)
    app.dependency_overrides[get_login_ip_rate_limiter] = lambda: limiter
    await client.post("/auth/register", json={"email": "ipone@b.com", "password": "s3cret!pass"})
    await client.post("/auth/register", json={"email": "iptwo@b.com", "password": "s3cret!pass"})

    first = await client.post(
        "/auth/login", json={"email": "ipone@b.com", "password": "s3cret!pass"}
    )
    assert first.status_code == 200, first.text

    # A DIFFERENT email, same test-client IP: the (ip, email) limiter alone
    # would treat this as a fresh bucket and allow it — the IP-only limiter
    # must still block it.
    second = await client.post(
        "/auth/login", json={"email": "iptwo@b.com", "password": "s3cret!pass"}
    )
    assert second.status_code == 429, second.text


@pytest.mark.asyncio
async def test_change_password_succeeds_with_correct_old_password(client):
    reg = await client.post("/auth/register", json={"email": "cp@b.com", "password": "s3cret!pass"})
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    resp = await client.post(
        "/auth/password",
        json={"old_password": "s3cret!pass", "new_password": "n3w!password"},
        headers=headers,
    )
    assert resp.status_code == 204, resp.text

    # The OLD password must actually stop working — a bug that changed the
    # response but not the persisted hash (e.g. saving a detached/stale ORM
    # instance) would leave every other assertion here green.
    old_login = await client.post(
        "/auth/login", json={"email": "cp@b.com", "password": "s3cret!pass"}
    )
    assert old_login.status_code == 401
    new_login = await client.post(
        "/auth/login", json={"email": "cp@b.com", "password": "n3w!password"}
    )
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_change_password_is_rate_limited(client):
    # #300: a stolen access token (short-lived, but not the password) must not be
    # able to brute-force old_password unthrottled — symmetric to login.
    limiter = InMemoryRateLimiter(max_hits=2, window_seconds=60)
    app.dependency_overrides[get_change_password_rate_limiter] = lambda: limiter
    reg = await client.post(
        "/auth/register", json={"email": "cprl@b.com", "password": "s3cret!pass"}
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    attempt = {"old_password": "WRONG", "new_password": "n3w!password"}

    assert (await client.post("/auth/password", json=attempt, headers=headers)).status_code == 401
    assert (await client.post("/auth/password", json=attempt, headers=headers)).status_code == 401
    blocked = await client.post("/auth/password", json=attempt, headers=headers)
    assert blocked.status_code == 429


@pytest.mark.asyncio
async def test_change_password_rate_limit_is_keyed_by_user_id_not_token_or_ip(client):
    # #300 explicitly requires per-user_id keying (the caller is authenticated,
    # unlike login/register) — NOT per-token and NOT per-IP.
    limiter = InMemoryRateLimiter(max_hits=1, window_seconds=60)
    app.dependency_overrides[get_change_password_rate_limiter] = lambda: limiter
    reg1 = await client.post(
        "/auth/register", json={"email": "cp1@b.com", "password": "s3cret!pass"}
    )
    token_a = reg1.json()["access_token"]
    attempt = {"old_password": "WRONG", "new_password": "n3w!password"}

    assert (
        await client.post(
            "/auth/password", json=attempt, headers={"Authorization": f"Bearer {token_a}"}
        )
    ).status_code == 401

    # A SECOND, DIFFERENT token for the SAME user — proves the key is user_id,
    # not the token/credentials string. If it were token-keyed, an attacker
    # could evade the throttle just by fetching a fresh token for the same
    # stolen account (e.g. via /auth/login) instead of reusing the exhausted one.
    login = await client.post("/auth/login", json={"email": "cp1@b.com", "password": "s3cret!pass"})
    token_b = login.json()["access_token"]
    assert token_b != token_a
    blocked = await client.post(
        "/auth/password", json=attempt, headers={"Authorization": f"Bearer {token_b}"}
    )
    assert blocked.status_code == 429

    # A DIFFERENT user, same test-client IP, own bucket — untouched by user 1's
    # block. If this were IP-keyed, user 2 would inherit user 1's block too.
    reg2 = await client.post(
        "/auth/register", json={"email": "cp2@b.com", "password": "s3cret!pass"}
    )
    headers2 = {"Authorization": f"Bearer {reg2.json()['access_token']}"}
    assert (await client.post("/auth/password", json=attempt, headers=headers2)).status_code == 401
