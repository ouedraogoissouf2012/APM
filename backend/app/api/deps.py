from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.domain.exceptions import AuthenticationError
from app.models.user import User
from app.repositories.user_repository import SqlAlchemyUserRepository, UserRepository
from app.services.auth_service import AuthService

_bearer = HTTPBearer(auto_error=False)


def get_user_repository(db: AsyncSession = Depends(get_db)) -> UserRepository:
    return SqlAlchemyUserRepository(db)


def get_auth_service(users: UserRepository = Depends(get_user_repository)) -> AuthService:
    return AuthService(users)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    service: AuthService = Depends(get_auth_service),
) -> User:
    if credentials is None:
        raise AuthenticationError("Not authenticated")
    return await service.get_authenticated_user(credentials.credentials)
