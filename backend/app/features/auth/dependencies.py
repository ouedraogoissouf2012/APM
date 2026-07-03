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

_settings = get_settings()

# Process-wide limiters. Swap any of these for RedisRateLimiter to scale across
# instances; the RateLimiter interface and route callers stay unchanged.
_register_rate_limiter = InMemoryRateLimiter(
    max_hits=_settings.register_rate_limit_max,
    window_seconds=_settings.register_rate_limit_window_seconds,
)
_login_rate_limiter = InMemoryRateLimiter(
    max_hits=_settings.login_rate_limit_max,
    window_seconds=_settings.login_rate_limit_window_seconds,
)
_refresh_rate_limiter = InMemoryRateLimiter(
    max_hits=_settings.refresh_rate_limit_max,
    window_seconds=_settings.refresh_rate_limit_window_seconds,
)
_conversation_rate_limiter = InMemoryRateLimiter(
    max_hits=_settings.conversation_rate_limit_max,
    window_seconds=_settings.conversation_rate_limit_window_seconds,
)
_debrief_rate_limiter = InMemoryRateLimiter(
    max_hits=_settings.debrief_rate_limit_max,
    window_seconds=_settings.debrief_rate_limit_window_seconds,
)


def get_register_rate_limiter() -> RateLimiter:
    return _register_rate_limiter


def get_login_rate_limiter() -> RateLimiter:
    return _login_rate_limiter


def get_refresh_rate_limiter() -> RateLimiter:
    return _refresh_rate_limiter


def get_conversation_rate_limiter() -> RateLimiter:
    return _conversation_rate_limiter


def get_debrief_rate_limiter() -> RateLimiter:
    return _debrief_rate_limiter


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
