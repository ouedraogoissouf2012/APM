import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.database import Base, get_db
from app.main import app


@pytest_asyncio.fixture(scope="session")
async def _engine():
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
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
