"""Authentication business logic.

Issues a short-lived access token plus a long-lived, rotating refresh token.
Refresh tokens are stored hashed; refreshing rotates (revokes the old, issues a
new one). Depends only on repository interfaces and pure security helpers.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.domain.exceptions import (
    AuthenticationError,
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)
from app.features.auth.models import User
from app.features.auth.repository import RefreshTokenRepository, UserRepository


@dataclass
class AuthResult:
    user: User
    access_token: str
    refresh_token: str


def normalize_email(email: str) -> str:
    """Canonical form for BOTH storage and lookup: trimmed + lowercased (#220).

    Emails are case-insensitive in practice, but `EmailStr` only lowercases the
    domain and neither register nor login normalised — so 'Jean@x.com' and
    'jean@x.com' were two accounts, and a mobile keyboard's auto-capitalisation
    could 401 a learner who typed the right password. Normalising here makes it a
    single account; a functional unique index on lower(email) guards it in the DB.
    """
    return email.strip().lower()


class AuthService:
    def __init__(
        self,
        users: UserRepository,
        refresh_tokens: RefreshTokenRepository,
        refresh_ttl_days: int,
    ) -> None:
        self._users = users
        self._refresh = refresh_tokens
        self._refresh_ttl_days = refresh_ttl_days

    async def _issue_tokens(self, user: User, *, commit: bool = True) -> AuthResult:
        raw_refresh = generate_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(days=self._refresh_ttl_days)
        await self._refresh.create(
            user_id=user.id,
            token_hash=hash_token(raw_refresh),
            expires_at=expires_at,
            commit=commit,
        )
        return AuthResult(
            user=user,
            access_token=create_access_token(subject=str(user.id)),
            refresh_token=raw_refresh,
        )

    async def register(self, email: str, password: str, native_language: str) -> AuthResult:
        email = normalize_email(email)
        if await self._users.get_by_email(email) is not None:
            raise EmailAlreadyExistsError("Email already registered")
        user = User(
            email=email,
            hashed_password=hash_password(password),
            native_language=native_language,
        )
        user = await self._users.create(user)
        return await self._issue_tokens(user)

    async def login(self, email: str, password: str) -> AuthResult:
        email = normalize_email(email)
        user = await self._users.get_by_email(email)
        if user is None or not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError("Invalid credentials")
        return await self._issue_tokens(user)

    async def refresh(self, raw_refresh_token: str) -> AuthResult:
        try:
            record = await self._refresh.lock_by_hash(hash_token(raw_refresh_token))
            now = datetime.now(UTC)
            if record is None or record.revoked_at is not None:
                raise InvalidRefreshTokenError("Invalid refresh token")
            expires_at = record.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= now:
                raise InvalidRefreshTokenError("Refresh token expired")
            user = await self._users.get_by_id(record.user_id)
            if user is None:
                raise InvalidRefreshTokenError("Invalid refresh token")

            # Single transaction: lock old token, revoke it, create replacement, commit.
            await self._refresh.revoke(record, revoked_at=now, commit=False)
            result = await self._issue_tokens(user, commit=False)
            await self._refresh.commit()
            return result
        except Exception:
            await self._refresh.rollback()
            raise

    async def logout(self, raw_refresh_token: str) -> None:
        record = await self._refresh.get_by_hash(hash_token(raw_refresh_token))
        if record is not None and record.revoked_at is None:
            await self._refresh.revoke(record, revoked_at=datetime.now(UTC))

    async def get_authenticated_user(self, token: str) -> User:
        try:
            subject = decode_access_token(token)
        except InvalidTokenError as exc:
            raise AuthenticationError("Invalid token") from exc
        user = await self._users.get_by_id(int(subject))
        if user is None:
            raise AuthenticationError("User not found")
        return user
