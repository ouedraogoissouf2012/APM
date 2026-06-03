from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.rate_limit import InMemoryRateLimiter, RateLimiter
from app.database import get_db
from app.domain.exceptions import AuthenticationError
from app.features.auth.models import User
from app.features.auth.repository import (
    RefreshTokenRepository,
    SqlAlchemyRefreshTokenRepository,
    SqlAlchemyUserRepository,
    UserRepository,
)
from app.features.auth.service import AuthService

_bearer = HTTPBearer(auto_error=False)

# Process-wide login limiter. Swap for a Redis-backed RateLimiter to scale across
# instances; the interface (and callers) stay unchanged.
_login_rate_limiter = InMemoryRateLimiter(
    max_hits=get_settings().login_rate_limit_max,
    window_seconds=get_settings().login_rate_limit_window_seconds,
)


def get_login_rate_limiter() -> RateLimiter:
    return _login_rate_limiter


def get_user_repository(db: AsyncSession = Depends(get_db)) -> UserRepository:
    return SqlAlchemyUserRepository(db)


def get_refresh_token_repository(db: AsyncSession = Depends(get_db)) -> RefreshTokenRepository:
    return SqlAlchemyRefreshTokenRepository(db)


def get_auth_service(
    users: UserRepository = Depends(get_user_repository),
    refresh_tokens: RefreshTokenRepository = Depends(get_refresh_token_repository),
) -> AuthService:
    return AuthService(users, refresh_tokens, get_settings().refresh_token_expire_days)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    service: AuthService = Depends(get_auth_service),
) -> User:
    if credentials is None:
        raise AuthenticationError("Not authenticated")
    return await service.get_authenticated_user(credentials.credentials)
