from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.idempotency.models import IdempotencyKey


class IdempotencyRepository(Protocol):
    async def get_response(self, user_id: int, key: str) -> str | None: ...

    async def remember(self, user_id: int, key: str, response: str) -> None: ...


class SqlAlchemyIdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_response(self, user_id: int, key: str) -> str | None:
        return await self._session.scalar(
            select(IdempotencyKey.response).where(
                IdempotencyKey.user_id == user_id,
                IdempotencyKey.key == key,
            )
        )

    async def remember(self, user_id: int, key: str, response: str) -> None:
        self._session.add(IdempotencyKey(user_id=user_id, key=key, response=response))
        await self._session.commit()
