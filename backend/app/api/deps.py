from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.rate_limit import InMemoryRateLimiter, RateLimiter
from app.database import get_db
from app.domain.exceptions import AuthenticationError
from app.models.user import User
from app.repositories.profile_repository import ProfileRepository, SqlAlchemyProfileRepository
from app.repositories.refresh_token_repository import (
    RefreshTokenRepository,
    SqlAlchemyRefreshTokenRepository,
)
from app.repositories.session_repository import SessionRepository, SqlAlchemySessionRepository
from app.repositories.user_repository import SqlAlchemyUserRepository, UserRepository
from app.services.auth_service import AuthService
from app.services.profile_service import ProfileService
from app.services.session_service import SessionService

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


def get_refresh_token_repository(
    db: AsyncSession = Depends(get_db),
) -> RefreshTokenRepository:
    return SqlAlchemyRefreshTokenRepository(db)


def get_auth_service(
    users: UserRepository = Depends(get_user_repository),
    refresh_tokens: RefreshTokenRepository = Depends(get_refresh_token_repository),
) -> AuthService:
    return AuthService(users, refresh_tokens, get_settings().refresh_token_expire_days)


def get_profile_repository(db: AsyncSession = Depends(get_db)) -> ProfileRepository:
    return SqlAlchemyProfileRepository(db)


def get_profile_service(
    profiles: ProfileRepository = Depends(get_profile_repository),
) -> ProfileService:
    return ProfileService(profiles)


def get_session_repository(db: AsyncSession = Depends(get_db)) -> SessionRepository:
    return SqlAlchemySessionRepository(db)


def get_session_service(
    sessions: SessionRepository = Depends(get_session_repository),
    users: UserRepository = Depends(get_user_repository),
) -> SessionService:
    return SessionService(sessions, users, get_settings().free_tier_daily_minutes)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    service: AuthService = Depends(get_auth_service),
) -> User:
    if credentials is None:
        raise AuthenticationError("Not authenticated")
    return await service.get_authenticated_user(credentials.credentials)
