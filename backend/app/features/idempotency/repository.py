from datetime import datetime
from typing import Protocol, cast

from sqlalchemy import CursorResult, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.idempotency.models import IdempotencyKey


class IdempotencyRepository(Protocol):
    async def lookup(self, user_id: int, key: str) -> tuple[bool, str | None]:
        """(exists, response). exists=False: no row. exists=True, response=None:
        claimed but still in flight. exists=True, response=str: completed."""
        ...

    async def claim(self, user_id: int, key: str, stale_before: datetime) -> bool:
        """Atomically reserve the key. Returns True iff THIS caller now owns it —
        either it inserted a fresh row, or it reclaimed a PENDING row older than
        `stale_before` (a claim abandoned by a crashed request). Returns False if
        a live claim or a completed result already exists."""
        ...

    async def complete(self, user_id: int, key: str, response: str) -> None: ...

    async def release(self, user_id: int, key: str) -> None:
        """Drop a claim whose work failed, so a later replay can re-claim it
        (avoids a poison key that would 409 forever)."""
        ...


class SqlAlchemyIdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lookup(self, user_id: int, key: str) -> tuple[bool, str | None]:
        row = await self._session.execute(
            select(IdempotencyKey.response).where(
                IdempotencyKey.user_id == user_id,
                IdempotencyKey.key == key,
            )
        )
        found = row.first()
        if found is None:
            return (False, None)
        return (True, found[0])

    async def claim(self, user_id: int, key: str, stale_before: datetime) -> bool:
        # INSERT ... ON CONFLICT DO UPDATE guarded by a WHERE: the unique
        # (user_id, key) constraint serialises concurrent callers, so at most one
        # wins. The DO UPDATE only fires for a PENDING (response IS NULL) row whose
        # claim is stale — reclaiming a turn abandoned by a crashed request. A live
        # pending claim or a completed row falls through to no-op (rowcount 0).
        stmt = (
            pg_insert(IdempotencyKey)
            .values(user_id=user_id, key=key, response=None, created_at=func.now())
            .on_conflict_do_update(
                constraint="uq_idempotency_user_key",
                set_={"created_at": func.now()},
                where=(
                    IdempotencyKey.response.is_(None) & (IdempotencyKey.created_at < stale_before)
                ),
            )
        )
        result = cast(CursorResult, await self._session.execute(stmt))
        await self._session.commit()
        return (result.rowcount or 0) == 1

    async def complete(self, user_id: int, key: str, response: str) -> None:
        await self._session.execute(
            update(IdempotencyKey)
            .where(IdempotencyKey.user_id == user_id, IdempotencyKey.key == key)
            .values(response=response)
        )
        await self._session.commit()

    async def release(self, user_id: int, key: str) -> None:
        await self._session.execute(
            delete(IdempotencyKey).where(
                IdempotencyKey.user_id == user_id, IdempotencyKey.key == key
            )
        )
        await self._session.commit()
