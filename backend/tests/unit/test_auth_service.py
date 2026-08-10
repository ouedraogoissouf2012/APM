from datetime import UTC, datetime, timedelta

import pytest

from app.core.security import create_access_token, decode_access_token, hash_token
from app.domain.exceptions import (
    AuthenticationError,
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    NotFoundError,
)
from app.features.auth.service import AuthService
from tests.unit.fakes import InMemoryRefreshTokenRepository, InMemoryUserRepository


def _service() -> AuthService:
    return AuthService(
        InMemoryUserRepository(),
        InMemoryRefreshTokenRepository(),
        refresh_ttl_days=30,
    )


def _backdate_revocation(service: AuthService, raw_token: str, *, seconds: int) -> None:
    """Simulate elapsed time since a token was rotated: move its revoked_at into the
    past so re-presenting it falls OUTSIDE the grace window — a theft replay, not a
    near-simultaneous retry. Reaches into the in-memory fake (a test double)."""
    record = service._refresh._by_hash[hash_token(raw_token)]  # type: ignore[attr-defined]
    record.revoked_at = datetime.now(UTC) - timedelta(seconds=seconds)


@pytest.mark.asyncio
async def test_register_creates_user_and_tokens():
    service = _service()
    result = await service.register("a@b.com", "s3cret!pass", "fr")
    assert result.user.email == "a@b.com"
    assert decode_access_token(result.access_token) == str(result.user.id)
    assert result.refresh_token  # opaque refresh token issued


@pytest.mark.asyncio
async def test_register_duplicate_email_raises():
    service = _service()
    await service.register("dup@b.com", "s3cret!pass", "fr")
    with pytest.raises(EmailAlreadyExistsError):
        await service.register("dup@b.com", "other!", "fr")


@pytest.mark.asyncio
async def test_email_is_stored_lowercased():
    # #220: EmailStr only lowercases the domain; register must canonicalise the
    # whole address so lookups and the unique index are case-insensitive.
    service = _service()
    result = await service.register("Jean.Dupont@GMail.com", "s3cret!pass", "fr")
    assert result.user.email == "jean.dupont@gmail.com"


@pytest.mark.asyncio
async def test_login_is_case_insensitive():
    # A mobile keyboard auto-capitalises the email at register; logging in with a
    # different case must still find the account (#220).
    service = _service()
    await service.register("Case@Example.com", "s3cret!pass", "fr")
    result = await service.login("case@EXAMPLE.com", "s3cret!pass")
    assert result.user.email == "case@example.com"


@pytest.mark.asyncio
async def test_register_duplicate_differing_only_by_case_raises():
    service = _service()
    await service.register("Dup@x.com", "s3cret!pass", "fr")
    with pytest.raises(EmailAlreadyExistsError):
        await service.register("dup@x.com", "other!", "fr")


@pytest.mark.asyncio
async def test_login_succeeds_with_correct_password():
    service = _service()
    await service.register("log@b.com", "s3cret!pass", "fr")
    result = await service.login("log@b.com", "s3cret!pass")
    assert decode_access_token(result.access_token) == str(result.user.id)


@pytest.mark.asyncio
async def test_login_wrong_password_raises():
    service = _service()
    await service.register("x@b.com", "s3cret!pass", "fr")
    with pytest.raises(InvalidCredentialsError):
        await service.login("x@b.com", "nope")


@pytest.mark.asyncio
async def test_login_unknown_email_raises():
    service = _service()
    with pytest.raises(InvalidCredentialsError):
        await service.login("ghost@b.com", "whatever")


@pytest.mark.asyncio
async def test_refresh_rotates_and_returns_new_tokens():
    service = _service()
    reg = await service.register("r@b.com", "s3cret!pass", "fr")
    refreshed = await service.refresh(reg.refresh_token)
    assert refreshed.refresh_token != reg.refresh_token  # rotation
    assert decode_access_token(refreshed.access_token) == str(reg.user.id)


@pytest.mark.asyncio
async def test_refresh_with_used_token_is_rejected():
    service = _service()
    reg = await service.register("r2@b.com", "s3cret!pass", "fr")
    await service.refresh(reg.refresh_token)  # consumes/rotates it
    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh(reg.refresh_token)  # reuse rejected


@pytest.mark.asyncio
async def test_refresh_unknown_token_rejected():
    service = _service()
    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh("not-a-real-token")


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token():
    service = _service()
    reg = await service.register("lo@b.com", "s3cret!pass", "fr")
    await service.logout(reg.refresh_token)
    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh(reg.refresh_token)


@pytest.mark.asyncio
async def test_get_authenticated_user_returns_user():
    service = _service()
    reg = await service.register("me@b.com", "s3cret!pass", "fr")
    user = await service.get_authenticated_user(reg.access_token)
    assert user.email == "me@b.com"


@pytest.mark.asyncio
async def test_get_authenticated_user_invalid_token_raises():
    service = _service()
    with pytest.raises(AuthenticationError):
        await service.get_authenticated_user("not-a-jwt")


@pytest.mark.asyncio
async def test_get_authenticated_user_unknown_user_raises():
    service = _service()
    token = create_access_token(subject="999")
    with pytest.raises(AuthenticationError):
        await service.get_authenticated_user(token)


# ---- Account lifecycle (#232) ----


@pytest.mark.asyncio
async def test_deactivated_user_cannot_authenticate():
    service = _service()
    reg = await service.register("d@b.com", "s3cret!pass", "fr")
    reg.user.is_active = False  # an admin suspended the account
    with pytest.raises(AuthenticationError):
        await service.get_authenticated_user(reg.access_token)


@pytest.mark.asyncio
async def test_deactivated_user_cannot_refresh():
    service = _service()
    reg = await service.register("d2@b.com", "s3cret!pass", "fr")
    reg.user.is_active = False
    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh(reg.refresh_token)


@pytest.mark.asyncio
async def test_refresh_reuse_beyond_grace_revokes_the_whole_family():
    # Re-presenting a rotated token LONG after rotation is a theft replay: EVERY
    # session (incl. the attacker's freshly-rotated one) must die (#232).
    service = _service()
    reg = await service.register("reuse@b.com", "s3cret!pass", "fr")
    rotated = await service.refresh(reg.refresh_token)  # reg token now revoked
    _backdate_revocation(service, reg.refresh_token, seconds=120)  # past the grace window
    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh(reg.refresh_token)  # stale reuse -> revoke the family
    # The attacker's rotated token is now dead too.
    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh(rotated.refresh_token)


@pytest.mark.asyncio
async def test_refresh_reuse_within_grace_does_not_nuke_sessions():
    # A near-simultaneous benign retry (a network retry, or a second device racing
    # the rotation) must NOT log the learner out everywhere (#253): the stale token
    # is rejected, but the freshly-rotated one keeps working.
    service = _service()  # default 30 s grace
    reg = await service.register("benign@b.com", "s3cret!pass", "fr")
    rotated = await service.refresh(reg.refresh_token)  # reg.revoked_at = now
    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh(reg.refresh_token)  # stale token rejected...
    # ...but the family survives: the current session still refreshes.
    again = await service.refresh(rotated.refresh_token)
    assert again.refresh_token != rotated.refresh_token


@pytest.mark.asyncio
async def test_change_password_requires_old_and_revokes_sessions():
    service = _service()
    reg = await service.register("cp@b.com", "s3cret!pass", "fr")
    await service.change_password(reg.user, "s3cret!pass", "n3w!password")
    # The old session is revoked...
    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh(reg.refresh_token)
    # ...and the new password works.
    result = await service.login("cp@b.com", "n3w!password")
    assert result.user.id == reg.user.id


@pytest.mark.asyncio
async def test_change_password_wrong_old_raises():
    service = _service()
    reg = await service.register("cp2@b.com", "s3cret!pass", "fr")
    with pytest.raises(InvalidCredentialsError):
        await service.change_password(reg.user, "WRONG", "n3w!password")


@pytest.mark.asyncio
async def test_set_active_deactivates_and_revokes_sessions():
    service = _service()
    reg = await service.register("sa@b.com", "s3cret!pass", "fr")
    await service.set_active(reg.user.id, False)
    assert reg.user.is_active is False
    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh(reg.refresh_token)


@pytest.mark.asyncio
async def test_set_active_unknown_user_raises():
    service = _service()
    with pytest.raises(NotFoundError):
        await service.set_active(9999, False)
