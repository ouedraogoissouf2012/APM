from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.rate_limit import RateLimiter
from app.core.rate_limit_factory import build_rate_limiter
from app.database import get_db
from app.domain.exceptions import AuthenticationError, AuthorizationError
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

# Process-wide limiters, backend chosen from config (Redis when REDIS_URL is set,
# else in-memory with max_keys cap to prevent DoS via high-cardinality keys #234).
# The RateLimiter interface and route callers stay unchanged.
_register_rate_limiter = build_rate_limiter(
    namespace="register",
    max_hits=_settings.register_rate_limit_max,
    window_seconds=_settings.register_rate_limit_window_seconds,
    redis_url=_settings.redis_url,
    max_keys=_settings.rate_limit_max_keys,
)
_login_rate_limiter = build_rate_limiter(
    namespace="login",
    max_hits=_settings.login_rate_limit_max,
    window_seconds=_settings.login_rate_limit_window_seconds,
    redis_url=_settings.redis_url,
    max_keys=_settings.rate_limit_max_keys,
)
_refresh_rate_limiter = build_rate_limiter(
    namespace="refresh",
    max_hits=_settings.refresh_rate_limit_max,
    window_seconds=_settings.refresh_rate_limit_window_seconds,
    redis_url=_settings.redis_url,
    max_keys=_settings.rate_limit_max_keys,
)


def get_register_rate_limiter() -> RateLimiter:
    return _register_rate_limiter


def get_login_rate_limiter() -> RateLimiter:
    return _login_rate_limiter


def get_refresh_rate_limiter() -> RateLimiter:
    return _refresh_rate_limiter


def get_user_repository(db: AsyncSession = Depends(get_db)) -> UserRepository:
    return SqlAlchemyUserRepository(db)


def get_refresh_token_repository(db: AsyncSession = Depends(get_db)) -> RefreshTokenRepository:
    return SqlAlchemyRefreshTokenRepository(db)


def get_auth_service(
    users: UserRepository = Depends(get_user_repository),
    refresh_tokens: RefreshTokenRepository = Depends(get_refresh_token_repository),
) -> AuthService:
    settings = get_settings()
    return AuthService(
        users,
        refresh_tokens,
        settings.refresh_token_expire_days,
        reuse_grace_seconds=settings.refresh_reuse_grace_seconds,
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    service: AuthService = Depends(get_auth_service),
) -> User:
    if credentials is None:
        raise AuthenticationError("Not authenticated")
    return await service.get_authenticated_user(credentials.credentials)


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """Like get_current_user, but rejects non-admins with 403. Guards admin-only
    endpoints (e.g. changing a user's tier)."""
    if not current_user.is_admin:
        raise AuthorizationError("Admin privileges required")
    return current_user
