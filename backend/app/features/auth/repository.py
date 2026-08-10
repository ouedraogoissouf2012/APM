"""Auth-domain persistence: users and refresh tokens.

Repositories are Protocols (interfaces) with SQLAlchemy implementations, so
services depend on the interface and any substitutable fake works in unit tests.
"""

from datetime import datetime
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import EmailAlreadyExistsError
from app.features.auth.models import RefreshToken, User


class UserRepository(Protocol):
    async def get_by_id(self, user_id: int) -> User | None: ...

    async def get_by_email(self, email: str) -> User | None: ...

    async def create(self, user: User) -> User: ...

    async def save(self, user: User) -> User:
        """Persist changes made to an already-loaded user aggregate."""
        ...

    async def lock(self, user_id: int) -> User | None:
        """Fetch the user with a row lock (SELECT ... FOR UPDATE) for atomic updates."""
        ...


class SqlAlchemyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        return await self._session.scalar(select(User).where(User.email == email))

    async def create(self, user: User) -> User:
        self._session.add(user)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            # A concurrent registration won the race for this email between the
            # service's pre-check and this commit (#232 TOCTOU): translate the DB
            # uniqueness violation to a clean 409 instead of a raw 500.
            await self._session.rollback()
            raise EmailAlreadyExistsError("Email already registered") from exc
        await self._session.refresh(user)
        return user

    async def save(self, user: User) -> User:
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def lock(self, user_id: int) -> User | None:
        result = await self._session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()


class RefreshTokenRepository(Protocol):
    async def create(
        self,
        user_id: int,
        token_hash: str,
        expires_at: datetime,
        *,
        commit: bool = True,
    ) -> RefreshToken: ...

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None: ...

    async def lock_by_hash(self, token_hash: str) -> RefreshToken | None: ...

    async def revoke(
        self, token: RefreshToken, revoked_at: datetime, *, commit: bool = True
    ) -> None: ...

    async def revoke_all_for_user(
        self, user_id: int, revoked_at: datetime, *, commit: bool = True
    ) -> None:
        """Revoke every still-active refresh token of a user (reuse detection,
        password change, deactivation) — the 'log out everywhere' primitive."""
        ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class SqlAlchemyRefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: int,
        token_hash: str,
        expires_at: datetime,
        *,
        commit: bool = True,
    ) -> RefreshToken:
        token = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self._session.add(token)
        if commit:
            await self._session.commit()
            await self._session.refresh(token)
        else:
            await self._session.flush()
        return token

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        return await self._session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )

    async def lock_by_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self._session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
        )
        return result.scalar_one_or_none()

    async def revoke(
        self, token: RefreshToken, revoked_at: datetime, *, commit: bool = True
    ) -> None:
        token.revoked_at = revoked_at
        if commit:
            await self._session.commit()
        else:
            await self._session.flush()

    async def revoke_all_for_user(
        self, user_id: int, revoked_at: datetime, *, commit: bool = True
    ) -> None:
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )
        if commit:
            await self._session.commit()
        else:
            await self._session.flush()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
