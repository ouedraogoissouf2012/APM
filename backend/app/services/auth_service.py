"""Authentication business logic.

Depends only on the `UserRepository` interface and pure security helpers — no
FastAPI, no SQLAlchemy. Raises domain exceptions; the API layer maps them to HTTP.
"""

from dataclasses import dataclass

from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.domain.exceptions import (
    AuthenticationError,
    EmailAlreadyExistsError,
    InvalidCredentialsError,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository


@dataclass
class AuthResult:
    user: User
    access_token: str


class AuthService:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def register(self, email: str, password: str, native_language: str) -> AuthResult:
        if await self._users.get_by_email(email) is not None:
            raise EmailAlreadyExistsError("Email already registered")
        user = User(
            email=email,
            hashed_password=hash_password(password),
            native_language=native_language,
        )
        user = await self._users.create(user)
        return AuthResult(user=user, access_token=create_access_token(subject=str(user.id)))

    async def login(self, email: str, password: str) -> AuthResult:
        user = await self._users.get_by_email(email)
        if user is None or not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError("Invalid credentials")
        return AuthResult(user=user, access_token=create_access_token(subject=str(user.id)))

    async def get_authenticated_user(self, token: str) -> User:
        try:
            subject = decode_access_token(token)
        except InvalidTokenError as exc:
            raise AuthenticationError("Invalid token") from exc
        user = await self._users.get_by_id(int(subject))
        if user is None:
            raise AuthenticationError("User not found")
        return user
