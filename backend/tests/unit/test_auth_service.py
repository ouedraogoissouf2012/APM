import pytest

from app.core.security import create_access_token, decode_access_token
from app.domain.exceptions import (
    AuthenticationError,
    EmailAlreadyExistsError,
    InvalidCredentialsError,
)
from app.services.auth_service import AuthService
from tests.unit.fakes import InMemoryUserRepository


def _service() -> AuthService:
    return AuthService(InMemoryUserRepository())


@pytest.mark.asyncio
async def test_register_creates_user_and_valid_token():
    service = _service()
    result = await service.register("a@b.com", "s3cret!", "fr")
    assert result.user.email == "a@b.com"
    assert result.user.id == 1
    assert decode_access_token(result.access_token) == "1"


@pytest.mark.asyncio
async def test_register_duplicate_email_raises():
    service = _service()
    await service.register("dup@b.com", "s3cret!", "fr")
    with pytest.raises(EmailAlreadyExistsError):
        await service.register("dup@b.com", "other!", "fr")


@pytest.mark.asyncio
async def test_login_succeeds_with_correct_password():
    service = _service()
    await service.register("log@b.com", "s3cret!", "fr")
    result = await service.login("log@b.com", "s3cret!")
    assert decode_access_token(result.access_token) == str(result.user.id)


@pytest.mark.asyncio
async def test_login_wrong_password_raises():
    service = _service()
    await service.register("x@b.com", "s3cret!", "fr")
    with pytest.raises(InvalidCredentialsError):
        await service.login("x@b.com", "nope")


@pytest.mark.asyncio
async def test_login_unknown_email_raises():
    service = _service()
    with pytest.raises(InvalidCredentialsError):
        await service.login("ghost@b.com", "whatever")


@pytest.mark.asyncio
async def test_get_authenticated_user_returns_user():
    service = _service()
    reg = await service.register("me@b.com", "s3cret!", "fr")
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
