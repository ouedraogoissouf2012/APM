import pytest

from app.core.security import create_access_token, decode_access_token
from app.domain.exceptions import (
    AuthenticationError,
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)
from app.features.auth.service import AuthService
from tests.unit.fakes import InMemoryRefreshTokenRepository, InMemoryUserRepository


def _service() -> AuthService:
    return AuthService(
        InMemoryUserRepository(),
        InMemoryRefreshTokenRepository(),
        refresh_ttl_days=30,
    )


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
async def test_register_stores_email_lowercased():
    service = _service()
    result = await service.register("John.DOE@Gmail.COM", "s3cret!pass", "fr")
    assert result.user.email == "john.doe@gmail.com"


@pytest.mark.asyncio
async def test_register_duplicate_email_is_case_insensitive():
    service = _service()
    await service.register("user@example.com", "s3cret!pass", "fr")
    with pytest.raises(EmailAlreadyExistsError):
        await service.register("USER@Example.com", "other!pass", "fr")


@pytest.mark.asyncio
async def test_login_is_case_insensitive():
    service = _service()
    reg = await service.register("caps@b.com", "s3cret!pass", "fr")
    result = await service.login("CAPS@B.com", "s3cret!pass")
    assert decode_access_token(result.access_token) == str(reg.user.id)


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
