import os

# Force the fake LLM engines for the whole test run BEFORE the app (and its
# cached settings) are imported. Env vars take precedence over the .env file, so
# tests never call the real (paid) DeepSeek API and stay independent of whatever
# VOICE_ENGINE/DEBRIEF_ENGINE a developer has set locally.
os.environ["VOICE_ENGINE"] = "fake"
os.environ["DEBRIEF_ENGINE"] = "fake"

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings  # noqa: E402
from app.core.rate_limit import NoOpRateLimiter  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.features.auth.dependencies import (  # noqa: E402
    get_conversation_rate_limiter,
    get_debrief_rate_limiter,
    get_login_rate_limiter,
    get_refresh_rate_limiter,
    get_register_rate_limiter,
)
from app.main import app  # noqa: E402


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
