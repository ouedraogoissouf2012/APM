import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.core.rate_limit import NoOpRateLimiter
from app.database import Base, get_db
from app.features.auth.dependencies import (
    get_conversation_rate_limiter,
    get_debrief_rate_limiter,
    get_login_rate_limiter,
    get_refresh_rate_limiter,
    get_register_rate_limiter,
)
from app.main import app


@pytest_asyncio.fixture
async def _engine():
    # Function-scoped: each test gets its own engine in its own event loop.
    # asyncpg connections are loop-bound, so a session-scoped engine breaks
    # across pytest-asyncio's per-test loops ("another operation is in progress").
    settings = get_settings()
    assert settings.database_url_test, "DATABASE_URL_TEST must be set for tests"
    engine = create_async_engine(settings.database_url_test, future=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def _setup_db(_engine):
    """Fresh schema per test — drop+create before, drop after. Simple and isolated."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(_engine, _setup_db) -> AsyncClient:
    test_sessionmaker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db():
        async with test_sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    # Disable rate limiting by default so it doesn't leak across tests;
    # dedicated rate-limit tests override these with real limiters.
    app.dependency_overrides[get_register_rate_limiter] = lambda: NoOpRateLimiter()
    app.dependency_overrides[get_login_rate_limiter] = lambda: NoOpRateLimiter()
    app.dependency_overrides[get_refresh_rate_limiter] = lambda: NoOpRateLimiter()
    app.dependency_overrides[get_conversation_rate_limiter] = lambda: NoOpRateLimiter()
    app.dependency_overrides[get_debrief_rate_limiter] = lambda: NoOpRateLimiter()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def db_session(_engine, _setup_db):
    maker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
