from collections.abc import AsyncGenerator, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

IoBoundaryHook = Callable[[], Awaitable[None]]


class Base(DeclarativeBase):
    pass


_settings = get_settings()
engine = create_async_engine(
    _settings.database_url,
    echo=False,
    future=True,
    # Explicit pool (#354): get_current_user -> get_db holds this connection for
    # the whole request, including external LLM/STT/TTS calls (~seconds) — an
    # implicit default pool silently caps concurrency with no visibility into why.
    # pool_pre_ping avoids handing out a connection the server/network already
    # dropped; pool_recycle (config.py) bounds how long one can go unverified.
    pool_size=_settings.db_pool_size,
    max_overflow=_settings.db_max_overflow,
    pool_pre_ping=True,
    pool_recycle=_settings.db_pool_recycle_seconds,
    # Keep bound parameters OUT of error strings and logs. IntegrityError/DataError
    # (and any DB error reaching the exc_info catch-all) render their parameters via
    # str(exc) — which the 5xx / DB-error handlers log with exc_info — so an unhandled
    # unique-violation would otherwise leak credential-adjacent data (email, argon2
    # hash) and learner text into the logs. SQLAlchemy substitutes a placeholder while
    # keeping the statement + constraint name for diagnosis.
    hide_parameters=True,
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def release_request_connection(session: AsyncSession) -> None:
    """Hand a request's DB connection back to the pool before a long external I/O
    call, so it isn't held idle for seconds on the hot conversation paths (#399).

    `expunge_all()` DETACHES the ORM objects the session loaded so the following
    rollback can't EXPIRE them (an expired object lazy-reloads on next access — a
    stray query, or a MissingGreenlet inside a streaming task group). rollback()
    then ends the read transaction and returns the connection to the pool. Only
    safe when the caller has no pending writes on this session and reads only
    already-loaded column values afterwards (never a lazy relationship)."""
    session.expunge_all()
    await session.rollback()


def bind_io_boundary(session: AsyncSession) -> IoBoundaryHook:
    """Bind `session` into a no-arg hook that hands its connection back to the pool.

    Call after the last DB read and before a long external I/O (#399, #415). The
    session must have no pending writes; afterwards only already-loaded column
    values are safe to read (never a lazy relationship).
    """

    async def _release() -> None:
        await release_request_connection(session)

    return _release
