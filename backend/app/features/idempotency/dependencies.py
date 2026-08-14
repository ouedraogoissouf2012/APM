from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import get_db
from app.features.idempotency.repository import SqlAlchemyIdempotencyRepository
from app.features.idempotency.service import IdempotencyService

# A factory that opens a FRESH, short-lived IdempotencyService on its own DB
# connection. See get_fresh_idempotency_factory for why the streaming turn route
# needs this rather than the request-scoped service.
FreshIdempotencyFactory = Callable[[], AbstractAsyncContextManager[IdempotencyService]]


def get_idempotency_service(db: AsyncSession = Depends(get_db)) -> IdempotencyService:
    return IdempotencyService(SqlAlchemyIdempotencyRepository(db))


def get_fresh_idempotency_factory(db: AsyncSession = Depends(get_db)) -> FreshIdempotencyFactory:
    """Build a factory that opens a FRESH IdempotencyService per call, on its own
    short-lived DB connection bound to the same engine as the request (`db.bind`).

    The streaming turn route (#399) releases the request's DB connection at the
    LLM/TTS boundary so it isn't held idle for seconds. Its POST-I/O idempotency
    writes — completing the key, releasing a failed claim, releasing the turn lock in
    the SSE generator's `finally` — therefore cannot reuse the request session: it
    has handed its connection back, and re-checking one out from inside the
    StreamingResponse task group raises MissingGreenlet (a different greenlet than the
    one that created the session). Each op runs on a fresh session instead. These are
    tiny, already-committed-per-call writes (claim/complete/release each commit), so a
    fresh connection per op is correct and short-lived. `db.bind` is read lazily on
    first invocation (never at construction), mirroring the turn persistence
    factory so a db=None wiring test can't trip on it."""

    @asynccontextmanager
    async def _open() -> AsyncIterator[IdempotencyService]:
        maker = async_sessionmaker(bind=db.bind, class_=AsyncSession, expire_on_commit=False)
        async with maker() as session:
            yield IdempotencyService(SqlAlchemyIdempotencyRepository(session))

    return _open
