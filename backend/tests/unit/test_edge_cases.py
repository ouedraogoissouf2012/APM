from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.config import get_settings
from app.core import security
from app.core.security import InvalidTokenError
from app.domain.exceptions import AuthenticationError, InvalidRefreshTokenError
from app.features.auth.service import AuthService
from tests.unit.fakes import InMemoryRefreshTokenRepository, InMemoryUserRepository


def _jwt_with(payload: dict) -> str:
    s = get_settings()
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def _expired_access_token() -> str:
    return _jwt_with({"sub": "1", "exp": datetime.now(UTC) - timedelta(minutes=1)})


def test_decode_expired_token_raises():
    with pytest.raises(InvalidTokenError):
        security.decode_access_token(_expired_access_token())


def test_decode_token_without_subject_raises():
    token = _jwt_with({"exp": datetime.now(UTC) + timedelta(minutes=5)})
    with pytest.raises(InvalidTokenError):
        security.decode_access_token(token)


def _auth_service(refresh_ttl_days: int = 30) -> AuthService:
    return AuthService(
        InMemoryUserRepository(),
        InMemoryRefreshTokenRepository(),
        refresh_ttl_days=refresh_ttl_days,
    )


@pytest.mark.asyncio
async def test_get_authenticated_user_with_expired_token_raises():
    service = _auth_service()
    with pytest.raises(AuthenticationError):
        await service.get_authenticated_user(_expired_access_token())


@pytest.mark.asyncio
async def test_refresh_with_expired_token_raises():
    # Negative TTL -> the issued refresh token is already expired.
    service = _auth_service(refresh_ttl_days=-1)
    reg = await service.register("e@b.com", "s3cret!pass", "fr")
    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh(reg.refresh_token)
