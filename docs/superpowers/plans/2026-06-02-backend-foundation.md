# APM — Fondation Backend : Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundational backend for APM — accounts/auth, learner profiles, conversation sessions with quota enforcement, and LiveKit ephemeral-token issuance — fully tested via the API.

**Architecture:** A FastAPI service with async SQLAlchemy 2.0 over PostgreSQL. JWT bearer auth (Argon2 password hashing). Three tables (`users`, `learner_profiles`, `sessions`). The "start session" endpoint checks the user's daily-minute quota and mints a short-lived LiveKit room token; "end session" records duration and increments usage. The mobile app and voice agent (later sub-projects) consume these endpoints.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async + asyncpg), Alembic, Pydantic v2 + pydantic-settings, PyJWT, pwdlib[argon2], livekit-api, pytest + pytest-asyncio + httpx, uv (deps).

---

## File Structure

```
docker-compose.yml            # (repo root) PostgreSQL 17 service on host port 5433
docker/postgres/init/
  01-create-test-db.sql       # (repo root) creates the apm_test database
backend/
  pyproject.toml              # deps + tooling config
  .env.example                # documented env vars
  alembic.ini                 # alembic config
  app/
    __init__.py
    main.py                   # FastAPI app, router wiring, /health
    config.py                 # Settings (pydantic-settings)
    database.py               # async engine, session factory, Base
    models/
      __init__.py             # imports all models for Alembic metadata
      user.py                 # User (+ quota fields)
      learner_profile.py      # LearnerProfile
      session.py             # ConversationSession
    schemas/
      __init__.py
      auth.py                 # Register/Login/Token/UserOut
      profile.py              # ProfileOut/ProfileUpdate
      session.py             # SessionStartOut/SessionEndIn/SessionOut
    core/
      __init__.py
      security.py             # hash/verify password, create/decode JWT
      livekit.py              # mint LiveKit room token
    api/
      __init__.py
      deps.py                 # get_db, get_current_user
      routes/
        __init__.py
        auth.py               # POST /auth/register, /auth/login
        profile.py            # GET/PUT /me/profile
        sessions.py          # POST /sessions/start, /sessions/{id}/end
  migrations/
    env.py                    # async Alembic env
    script.py.mako
    versions/                 # generated migrations
  tests/
    __init__.py
    conftest.py               # async engine + db + client fixtures
    test_security.py
    test_auth.py
    test_profile.py
    test_sessions.py
```

**Conventions:** All paths below are relative to `backend/` unless noted. Run all commands from `backend/` unless noted. PostgreSQL runs in **Docker** (`docker-compose.yml` at the repo root) exposing port **5433** on the host; it auto-creates two databases `apm` (dev) and `apm_test` (tests).

---

### Task 1: Project scaffold, config, dependencies

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.env.example`
- Create: `backend/app/__init__.py` (empty)
- Create: `backend/app/config.py`
- Create: `backend/tests/__init__.py` (empty)

- [ ] **Step 1: Create `backend/pyproject.toml`**

```toml
[project]
name = "apm-backend"
version = "0.1.0"
description = "APM (Anglais Pour Moi) backend — foundation"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlalchemy[asyncio]>=2.0.36",
    "asyncpg>=0.30",
    "alembic>=1.14",
    "pydantic>=2.10",
    "pydantic-settings>=2.6",
    "pyjwt>=2.10",
    "pwdlib[argon2]>=0.2.1",
    "livekit-api>=0.8",
    "python-multipart>=0.0.12",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "httpx>=0.28",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.uv]
package = false
```

- [ ] **Step 2: Create `backend/.env.example`**

```bash
# PostgreSQL via Docker (voir docker-compose.yml à la racine du repo).
# Port hôte 5433 pour ne pas entrer en conflit avec un PostgreSQL local sur 5432.
DATABASE_URL=postgresql+asyncpg://apm:apm_dev_password@localhost:5433/apm
DATABASE_URL_TEST=postgresql+asyncpg://apm:apm_dev_password@localhost:5433/apm_test

# JWT
JWT_SECRET=change-me-in-production-use-a-long-random-string
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# LiveKit
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=devsecret-change-me
LIVEKIT_TOKEN_TTL_SECONDS=120

# Quota
FREE_TIER_DAILY_MINUTES=10
```

- [ ] **Step 3: Create `backend/app/config.py`**

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    database_url_test: str = ""

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080

    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    livekit_token_ttl_seconds: int = 120

    free_tier_daily_minutes: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Create empty `backend/app/__init__.py` and `backend/tests/__init__.py`**

```bash
# (create two empty files)
```

- [ ] **Step 5: Install dependencies**

Run (from `backend/`):
```bash
uv sync
```
Expected: a `.venv` is created and all dependencies install without error.

- [ ] **Step 6: Create `docker-compose.yml` at the REPO ROOT** (not in `backend/`)

```yaml
services:
  postgres:
    image: postgres:17-alpine
    container_name: apm-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: apm
      POSTGRES_PASSWORD: apm_dev_password
      POSTGRES_DB: apm
    ports:
      - "5433:5432"  # host 5433 -> container 5432 (avoids clash with a local PostgreSQL on 5432)
    volumes:
      - apm_pgdata:/var/lib/postgresql/data
      - ./docker/postgres/init:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U apm -d apm"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  apm_pgdata:
```

- [ ] **Step 7: Create the test-DB init script `docker/postgres/init/01-create-test-db.sql`** (at repo root)

```sql
CREATE DATABASE apm_test;
```
(The `apm` database is created by `POSTGRES_DB`; this adds the test database. Scripts in `/docker-entrypoint-initdb.d` run once on first volume creation.)

- [ ] **Step 8: Start the database container**

Run (from the repo root):
```bash
docker compose up -d postgres
```
Verify it is healthy:
```bash
docker compose ps
```
Expected: `apm-postgres` is `running (healthy)` and listening on `0.0.0.0:5433->5432`.

- [ ] **Step 9: Create `backend/.env` from the example**

```bash
cp .env.example .env
```
Expected: `backend/.env` exists with the Docker connection string (port 5433, user `apm`).

- [ ] **Step 10: Commit**

```bash
git add docker-compose.yml docker/postgres/init/01-create-test-db.sql backend/pyproject.toml backend/uv.lock backend/.env.example backend/app/__init__.py backend/app/config.py backend/tests/__init__.py
git commit -m "chore(backend): scaffold project, config, deps, dockerized postgres"
```

---

### Task 2: Database engine, Base, and models metadata

**Files:**
- Create: `backend/app/database.py`
- Create: `backend/app/models/__init__.py`

- [ ] **Step 1: Create `backend/app/database.py`**

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
engine = create_async_engine(_settings.database_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
```

- [ ] **Step 2: Create `backend/app/models/__init__.py`** (only `Base` for now)

```python
from app.database import Base

__all__ = ["Base"]
```

> Each model task (3, 10, 12) appends its own import here so Alembic's autogenerate sees the new table. Importing a model module is what registers its table on `Base.metadata`. We build this up incrementally to avoid importing models that don't exist yet.

- [ ] **Step 3: Commit**

```bash
git add backend/app/database.py backend/app/models/__init__.py
git commit -m "feat(backend): async SQLAlchemy engine, Base, models metadata"
```

---

### Task 3: User model

**Files:**
- Create: `backend/app/models/user.py`

- [ ] **Step 1: Create `backend/app/models/user.py`**

```python
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    native_language: Mapped[str] = mapped_column(String(8), default="fr", nullable=False)
    cefr_level: Mapped[str] = mapped_column(String(2), default="A1", nullable=False)
    tier: Mapped[str] = mapped_column(String(16), default="free", nullable=False)

    # Daily quota tracking (reset when quota_date rolls over)
    quota_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    minutes_used_today: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 2: Register the model in `backend/app/models/__init__.py`**

Replace the file contents with:
```python
from app.database import Base
from app.models.user import User

__all__ = ["Base", "User"]
```

- [ ] **Step 3: Verify it imports**

Run:
```bash
uv run python -c "from app.models import User; print(User.__tablename__)"
```
Expected: prints `users`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/user.py backend/app/models/__init__.py
git commit -m "feat(backend): User model with quota fields"
```

---

### Task 4: Alembic setup + initial migration (users)

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/migrations/env.py`
- Create: `backend/migrations/script.py.mako`
- Create (generated): `backend/migrations/versions/<hash>_initial.py`

- [ ] **Step 1: Create `backend/alembic.ini`**

```ini
[alembic]
script_location = migrations
prepend_sys_path = .
version_path_separator = os

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 2: Create `backend/migrations/script.py.mako`**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 3: Create `backend/migrations/env.py` (async)**

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool

from app.config import get_settings
from app.models import Base  # noqa: F401  (registers all models)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_offline() -> None:
    context.configure(url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
```

- [ ] **Step 4: Generate the initial migration**

Run:
```bash
uv run alembic revision --autogenerate -m "initial users"
```
Expected: a file appears in `migrations/versions/` containing `op.create_table("users", ...)`.

- [ ] **Step 5: Apply the migration**

Run:
```bash
uv run alembic upgrade head
```
Expected: completes without error; the `users` table now exists in the `apm` database.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic.ini backend/migrations
git commit -m "feat(backend): alembic async setup + initial users migration"
```

---

### Task 5: Password hashing & JWT utilities (TDD)

**Files:**
- Create: `backend/app/core/__init__.py` (empty)
- Create: `backend/app/core/security.py`
- Test: `backend/tests/test_security.py`

- [ ] **Step 1: Write the failing test — `backend/tests/test_security.py`**

```python
import time

import pytest

from app.core import security


def test_password_hash_roundtrip():
    hashed = security.hash_password("s3cret!")
    assert hashed != "s3cret!"
    assert security.verify_password("s3cret!", hashed) is True
    assert security.verify_password("wrong", hashed) is False


def test_jwt_roundtrip():
    token = security.create_access_token(subject="42")
    assert security.decode_access_token(token) == "42"


def test_jwt_rejects_tampered_token():
    token = security.create_access_token(subject="42")
    with pytest.raises(security.InvalidTokenError):
        security.decode_access_token(token + "x")
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
uv run pytest tests/test_security.py -v
```
Expected: FAIL — `AttributeError`/`ImportError` (module/functions not defined).

- [ ] **Step 3: Create `backend/app/core/__init__.py`** (empty), then `backend/app/core/security.py`**

```python
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from app.config import get_settings

_pwd = PasswordHash.recommended()


class InvalidTokenError(Exception):
    pass


def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


def create_access_token(subject: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    subject = payload.get("sub")
    if subject is None:
        raise InvalidTokenError("missing subject")
    return subject
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
uv run pytest tests/test_security.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/__init__.py backend/app/core/security.py backend/tests/test_security.py
git commit -m "feat(backend): password hashing + JWT utilities (tested)"
```

---

### Task 6: Test fixtures (async engine, db, client)

**Files:**
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Create `backend/tests/conftest.py`**

```python
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
```

> Note: this imports `app.main:app`, created in Task 7. Don't run it until then. Each test gets a fresh schema; the app uses real sessions with real commits (no transaction-rollback trickery), which avoids the SQLAlchemy "commit inside an external transaction" pitfall.

- [ ] **Step 2: Commit**

```bash
git add backend/tests/conftest.py
git commit -m "test(backend): async engine/db/client fixtures"
```

---

### Task 7: Auth schemas, deps, app wiring, and register endpoint (TDD)

**Files:**
- Create: `backend/app/schemas/__init__.py` (empty)
- Create: `backend/app/schemas/auth.py`
- Create: `backend/app/api/__init__.py` (empty)
- Create: `backend/app/api/routes/__init__.py` (empty)
- Create: `backend/app/api/routes/auth.py`
- Create: `backend/app/main.py`
- Test: `backend/tests/test_auth.py`

- [ ] **Step 1: Write the failing test — `backend/tests/test_auth.py`**

```python
import pytest


@pytest.mark.asyncio
async def test_register_returns_token_and_user(client):
    resp = await client.post(
        "/auth/register",
        json={"email": "a@b.com", "password": "s3cret!", "native_language": "fr"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "a@b.com"
    assert body["user"]["cefr_level"] == "A1"


@pytest.mark.asyncio
async def test_register_duplicate_email_rejected(client):
    payload = {"email": "dup@b.com", "password": "s3cret!"}
    first = await client.post("/auth/register", json=payload)
    assert first.status_code == 201
    second = await client.post("/auth/register", json=payload)
    assert second.status_code == 409
```

- [ ] **Step 2: Create `backend/app/schemas/auth.py`** (and empty `backend/app/schemas/__init__.py`)

```python
from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    native_language: str = "fr"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    native_language: str
    cefr_level: str
    tier: str

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
```

> `EmailStr` requires `email-validator`; add it: run `uv add email-validator`.

- [ ] **Step 3: Create `backend/app/api/routes/auth.py`** (and empty `__init__.py` files for `app/api` and `app/api/routes`)

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.database import get_db
from app.models.user import User
from app.schemas.auth import LoginIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterIn, db: AsyncSession = Depends(get_db)) -> TokenOut:
    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        native_language=payload.native_language,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    token = create_access_token(subject=str(user.id))
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
async def login(payload: LoginIn, db: AsyncSession = Depends(get_db)) -> TokenOut:
    user = await db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(subject=str(user.id))
    return TokenOut(access_token=token, user=UserOut.model_validate(user))
```

- [ ] **Step 4: Create `backend/app/main.py`**

```python
from fastapi import FastAPI

from app.api.routes import auth

app = FastAPI(title="APM Backend")

app.include_router(auth.router)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 5: Run the test to verify it passes**

Run:
```bash
uv run pytest tests/test_auth.py -v
```
Expected: 2 passed (`test_register_returns_token_and_user`, `test_register_duplicate_email_rejected`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas backend/app/api backend/app/main.py backend/tests/test_auth.py backend/pyproject.toml backend/uv.lock
git commit -m "feat(backend): register endpoint + auth schemas + app wiring (tested)"
```

---

### Task 8: Login endpoint test (TDD)

**Files:**
- Modify: `backend/tests/test_auth.py` (append)

- [ ] **Step 1: Append the failing tests to `backend/tests/test_auth.py`**

```python
@pytest.mark.asyncio
async def test_login_succeeds_with_correct_password(client):
    await client.post("/auth/register", json={"email": "log@b.com", "password": "s3cret!"})
    resp = await client.post("/auth/login", json={"email": "log@b.com", "password": "s3cret!"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]


@pytest.mark.asyncio
async def test_login_fails_with_wrong_password(client):
    await client.post("/auth/register", json={"email": "log2@b.com", "password": "s3cret!"})
    resp = await client.post("/auth/login", json={"email": "log2@b.com", "password": "nope"})
    assert resp.status_code == 401
```

- [ ] **Step 2: Run the tests**

Run:
```bash
uv run pytest tests/test_auth.py -v
```
Expected: 4 passed (login logic was implemented in Task 7).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_auth.py
git commit -m "test(backend): login endpoint coverage"
```

---

### Task 9: `get_current_user` dependency (TDD)

**Files:**
- Create: `backend/app/api/deps.py`
- Modify: `backend/app/api/routes/auth.py` (add `GET /auth/me`)
- Modify: `backend/tests/test_auth.py` (append)

- [ ] **Step 1: Append the failing test to `backend/tests/test_auth.py`**

```python
@pytest.mark.asyncio
async def test_me_returns_current_user(client):
    reg = await client.post("/auth/register", json={"email": "me@b.com", "password": "s3cret!"})
    token = reg.json()["access_token"]
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == "me@b.com"


@pytest.mark.asyncio
async def test_me_rejects_missing_token(client):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run to verify it fails**

Run:
```bash
uv run pytest tests/test_auth.py::test_me_returns_current_user -v
```
Expected: FAIL — 404 (route not defined yet).

- [ ] **Step 3: Create `backend/app/api/deps.py`**

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import InvalidTokenError, decode_access_token
from app.database import get_db
from app.models.user import User

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        subject = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = await db.get(User, int(subject))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
```

- [ ] **Step 4: Add `GET /auth/me` to `backend/app/api/routes/auth.py`**

At the top, extend the imports:
```python
from app.api.deps import get_current_user
```
Append at the end of the file:
```python
@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)
```

- [ ] **Step 5: Run to verify it passes**

Run:
```bash
uv run pytest tests/test_auth.py -v
```
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/deps.py backend/app/api/routes/auth.py backend/tests/test_auth.py
git commit -m "feat(backend): get_current_user dependency + /auth/me (tested)"
```

---

### Task 10: LearnerProfile model + migration

**Files:**
- Create: `backend/app/models/learner_profile.py`
- Create (generated): `backend/migrations/versions/<hash>_learner_profiles.py`

- [ ] **Step 1: Create `backend/app/models/learner_profile.py`**

```python
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LearnerProfile(Base):
    __tablename__ = "learner_profiles"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    interests: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    goal: Mapped[str | None] = mapped_column(String(500), nullable=True)
    correction_intensity: Mapped[str] = mapped_column(String(16), default="gentle", nullable=False)
    accent: Mapped[str] = mapped_column(String(8), default="us", nullable=False)
```

- [ ] **Step 2: Register the model in `backend/app/models/__init__.py`**

Replace the file contents with:
```python
from app.database import Base
from app.models.learner_profile import LearnerProfile
from app.models.user import User

__all__ = ["Base", "User", "LearnerProfile"]
```

- [ ] **Step 3: Generate the migration**

Run:
```bash
uv run alembic revision --autogenerate -m "learner_profiles"
```
Expected: a new version file with `op.create_table("learner_profiles", ...)`.

- [ ] **Step 4: Apply it**

Run:
```bash
uv run alembic upgrade head
```
Expected: completes; `learner_profiles` table exists.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/learner_profile.py backend/app/models/__init__.py backend/migrations/versions
git commit -m "feat(backend): LearnerProfile model + migration"
```

---

### Task 11: Profile endpoints (TDD)

**Files:**
- Create: `backend/app/schemas/profile.py`
- Create: `backend/app/api/routes/profile.py`
- Modify: `backend/app/main.py` (include router)
- Test: `backend/tests/test_profile.py`

- [ ] **Step 1: Write the failing test — `backend/tests/test_profile.py`**

```python
import pytest


async def _auth_header(client):
    reg = await client.post("/auth/register", json={"email": "p@b.com", "password": "s3cret!"})
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


@pytest.mark.asyncio
async def test_get_profile_returns_defaults(client):
    headers = await _auth_header(client)
    resp = await client.get("/me/profile", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["interests"] == []
    assert body["correction_intensity"] == "gentle"
    assert body["accent"] == "us"


@pytest.mark.asyncio
async def test_update_profile_persists(client):
    headers = await _auth_header(client)
    resp = await client.put(
        "/me/profile",
        headers=headers,
        json={"interests": ["football", "cinema"], "goal": "job interview", "accent": "uk"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["interests"] == ["football", "cinema"]
    assert body["goal"] == "job interview"
    assert body["accent"] == "uk"

    # Persisted across requests
    again = await client.get("/me/profile", headers=headers)
    assert again.json()["interests"] == ["football", "cinema"]
```

- [ ] **Step 2: Run to verify it fails**

Run:
```bash
uv run pytest tests/test_profile.py -v
```
Expected: FAIL — 404 (routes not defined).

- [ ] **Step 3: Create `backend/app/schemas/profile.py`**

```python
from pydantic import BaseModel


class ProfileOut(BaseModel):
    interests: list[str]
    goal: str | None
    correction_intensity: str
    accent: str

    model_config = {"from_attributes": True}


class ProfileUpdate(BaseModel):
    interests: list[str] | None = None
    goal: str | None = None
    correction_intensity: str | None = None
    accent: str | None = None
```

- [ ] **Step 4: Create `backend/app/api/routes/profile.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.learner_profile import LearnerProfile
from app.models.user import User
from app.schemas.profile import ProfileOut, ProfileUpdate

router = APIRouter(prefix="/me/profile", tags=["profile"])


async def _get_or_create(db: AsyncSession, user_id: int) -> LearnerProfile:
    profile = await db.get(LearnerProfile, user_id)
    if profile is None:
        profile = LearnerProfile(user_id=user_id)
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    return profile


@router.get("", response_model=ProfileOut)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    profile = await _get_or_create(db, current_user.id)
    return ProfileOut.model_validate(profile)


@router.put("", response_model=ProfileOut)
async def update_profile(
    payload: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    profile = await _get_or_create(db, current_user.id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(profile, key, value)
    await db.commit()
    await db.refresh(profile)
    return ProfileOut.model_validate(profile)
```

- [ ] **Step 5: Include the router in `backend/app/main.py`**

Change the imports line:
```python
from app.api.routes import auth, profile
```
And after `app.include_router(auth.router)` add:
```python
app.include_router(profile.router)
```

- [ ] **Step 6: Run to verify it passes**

Run:
```bash
uv run pytest tests/test_profile.py -v
```
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/profile.py backend/app/api/routes/profile.py backend/app/main.py backend/tests/test_profile.py
git commit -m "feat(backend): learner profile GET/PUT endpoints (tested)"
```

---

### Task 12: ConversationSession model + migration

**Files:**
- Create: `backend/app/models/session.py`
- Create (generated): `backend/migrations/versions/<hash>_sessions.py`

- [ ] **Step 1: Create `backend/app/models/session.py`**

```python
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ConversationSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False)  # "scenario" | "free"
    scenario_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    room_name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    voice_engine: Mapped[str] = mapped_column(String(16), default="pipeline", nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
```

- [ ] **Step 2: Register the model in `backend/app/models/__init__.py`**

Replace the file contents with:
```python
from app.database import Base
from app.models.learner_profile import LearnerProfile
from app.models.session import ConversationSession
from app.models.user import User

__all__ = ["Base", "User", "LearnerProfile", "ConversationSession"]
```

- [ ] **Step 3: Generate and apply the migration**

Run:
```bash
uv run alembic revision --autogenerate -m "sessions"
uv run alembic upgrade head
```
Expected: a version file with `op.create_table("sessions", ...)`; upgrade succeeds.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/session.py backend/app/models/__init__.py backend/migrations/versions
git commit -m "feat(backend): ConversationSession model + migration"
```

---

### Task 13: LiveKit token + quota service (TDD)

**Files:**
- Create: `backend/app/core/livekit.py`
- Create: `backend/app/core/quota.py`
- Test: `backend/tests/test_sessions.py` (quota unit tests first)

- [ ] **Step 1: Write the failing unit tests — `backend/tests/test_sessions.py`**

```python
from datetime import date, timedelta

import pytest

from app.core import quota
from app.core.livekit import build_room_token
from app.models.user import User


def _make_user(**kw) -> User:
    defaults = dict(id=1, email="q@b.com", hashed_password="x", tier="free")
    defaults.update(kw)
    return User(**defaults)


def test_quota_resets_on_new_day():
    user = _make_user(quota_date=date.today() - timedelta(days=1), minutes_used_today=9.0)
    remaining = quota.remaining_minutes(user, free_daily=10, today=date.today())
    assert remaining == 10.0  # yesterday's usage is wiped


def test_quota_counts_today_usage():
    user = _make_user(quota_date=date.today(), minutes_used_today=7.0)
    remaining = quota.remaining_minutes(user, free_daily=10, today=date.today())
    assert remaining == 3.0


def test_premium_user_has_unlimited():
    user = _make_user(tier="premium", quota_date=date.today(), minutes_used_today=999.0)
    remaining = quota.remaining_minutes(user, free_daily=10, today=date.today())
    assert remaining == float("inf")


def test_record_usage_resets_then_adds():
    user = _make_user(quota_date=date.today() - timedelta(days=1), minutes_used_today=9.0)
    quota.record_usage(user, minutes=2.0, today=date.today())
    assert user.quota_date == date.today()
    assert user.minutes_used_today == 2.0


def test_build_room_token_returns_jwt():
    token = build_room_token(identity="user-1", room="session-1")
    assert isinstance(token, str)
    assert token.count(".") == 2  # header.payload.signature
```

- [ ] **Step 2: Run to verify it fails**

Run:
```bash
uv run pytest tests/test_sessions.py -v
```
Expected: FAIL — modules `app.core.quota` / `app.core.livekit` not found.

- [ ] **Step 3: Create `backend/app/core/quota.py`**

```python
from datetime import date

from app.models.user import User


def remaining_minutes(user: User, free_daily: int, today: date) -> float:
    if user.tier != "free":
        return float("inf")
    used = user.minutes_used_today if user.quota_date == today else 0.0
    return max(0.0, free_daily - used)


def record_usage(user: User, minutes: float, today: date) -> None:
    if user.quota_date != today:
        user.quota_date = today
        user.minutes_used_today = 0.0
    user.minutes_used_today += minutes
```

- [ ] **Step 4: Create `backend/app/core/livekit.py`**

```python
from livekit import api

from app.config import get_settings


def build_room_token(identity: str, room: str) -> str:
    settings = get_settings()
    grants = api.VideoGrants(room_join=True, room=room)
    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(grants)
        .with_ttl(__import__("datetime").timedelta(seconds=settings.livekit_token_ttl_seconds))
    )
    return token.to_jwt()
```

> Cleaner import: put `from datetime import timedelta` at the top and use `.with_ttl(timedelta(seconds=settings.livekit_token_ttl_seconds))`. Replace the inline `__import__` accordingly.

- [ ] **Step 5: Run to verify it passes**

Run:
```bash
uv run pytest tests/test_sessions.py -v
```
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/quota.py backend/app/core/livekit.py backend/tests/test_sessions.py
git commit -m "feat(backend): quota logic + LiveKit token builder (tested)"
```

---

### Task 14: Session start/end endpoints (TDD)

**Files:**
- Create: `backend/app/schemas/session.py`
- Create: `backend/app/api/routes/sessions.py`
- Modify: `backend/app/main.py` (include router)
- Modify: `backend/tests/test_sessions.py` (append API tests)

- [ ] **Step 1: Append failing API tests to `backend/tests/test_sessions.py`**

```python
async def _auth_header(client, email="s@b.com"):
    reg = await client.post("/auth/register", json={"email": email, "password": "s3cret!"})
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


@pytest.mark.asyncio
async def test_start_session_returns_token_and_room(client):
    headers = await _auth_header(client)
    resp = await client.post(
        "/sessions/start", headers=headers, json={"mode": "scenario", "scenario_id": "restaurant"}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["session_id"]
    assert body["room_name"]
    assert body["livekit_token"].count(".") == 2
    assert body["livekit_url"] is not None


@pytest.mark.asyncio
async def test_end_session_records_duration_and_usage(client):
    headers = await _auth_header(client, email="s2@b.com")
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]

    resp = await client.post(
        f"/sessions/{session_id}/end", headers=headers, json={"duration_minutes": 4.5}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["duration_minutes"] == 4.5


@pytest.mark.asyncio
async def test_start_session_blocked_when_quota_exhausted(client):
    headers = await _auth_header(client, email="s3@b.com")
    # Burn the full free daily quota in one session.
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    sid = start.json()["session_id"]
    await client.post(f"/sessions/{sid}/end", headers=headers, json={"duration_minutes": 10.0})

    blocked = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    assert blocked.status_code == 402  # Payment Required (quota exhausted)
```

- [ ] **Step 2: Run to verify it fails**

Run:
```bash
uv run pytest tests/test_sessions.py -v
```
Expected: the 3 new API tests FAIL (404), the 5 unit tests still pass.

- [ ] **Step 3: Create `backend/app/schemas/session.py`**

```python
from pydantic import BaseModel, Field


class SessionStartIn(BaseModel):
    mode: str = Field(pattern="^(scenario|free)$")
    scenario_id: str | None = None


class SessionStartOut(BaseModel):
    session_id: int
    room_name: str
    livekit_token: str
    livekit_url: str


class SessionEndIn(BaseModel):
    duration_minutes: float = Field(ge=0)


class SessionOut(BaseModel):
    id: int
    mode: str
    scenario_id: str | None
    duration_minutes: float | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Create `backend/app/api/routes/sessions.py`**

```python
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import get_settings
from app.core import quota
from app.core.livekit import build_room_token
from app.database import get_db
from app.models.session import ConversationSession
from app.models.user import User
from app.schemas.session import SessionEndIn, SessionOut, SessionStartIn, SessionStartOut

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/start", response_model=SessionStartOut, status_code=status.HTTP_201_CREATED)
async def start_session(
    payload: SessionStartIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionStartOut:
    settings = get_settings()
    if quota.remaining_minutes(current_user, settings.free_tier_daily_minutes, date.today()) <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Daily free quota exhausted",
        )
    session = ConversationSession(
        user_id=current_user.id,
        mode=payload.mode,
        scenario_id=payload.scenario_id,
        room_name=f"apm-{current_user.id}-{datetime.now(timezone.utc).timestamp():.0f}",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    token = build_room_token(identity=f"user-{current_user.id}", room=session.room_name)
    return SessionStartOut(
        session_id=session.id,
        room_name=session.room_name,
        livekit_token=token,
        livekit_url=settings.livekit_url,
    )


@router.post("/{session_id}/end", response_model=SessionOut)
async def end_session(
    session_id: int,
    payload: SessionEndIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionOut:
    session = await db.get(ConversationSession, session_id)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session.ended_at = datetime.now(timezone.utc)
    session.duration_minutes = payload.duration_minutes
    quota.record_usage(current_user, payload.duration_minutes, date.today())
    await db.commit()
    await db.refresh(session)
    return SessionOut.model_validate(session)
```

- [ ] **Step 5: Include the router in `backend/app/main.py`**

Change the import line to:
```python
from app.api.routes import auth, profile, sessions
```
And add after the profile include:
```python
app.include_router(sessions.router)
```

- [ ] **Step 6: Run the full test for this module**

Run:
```bash
uv run pytest tests/test_sessions.py -v
```
Expected: 8 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/session.py backend/app/api/routes/sessions.py backend/app/main.py backend/tests/test_sessions.py
git commit -m "feat(backend): session start/end with quota + LiveKit token (tested)"
```

---

### Task 15: Full suite + run the server (verification)

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run:
```bash
uv run pytest -v
```
Expected: all tests pass (security: 3, auth: 6, profile: 2, sessions: 8).

- [ ] **Step 2: Boot the server and hit `/health`**

Run (in one terminal):
```bash
uv run uvicorn app.main:app --reload
```
In another:
```bash
curl http://127.0.0.1:8000/health
```
Expected: `{"status":"ok"}`. Also open `http://127.0.0.1:8000/docs` and confirm `auth`, `profile`, `sessions` routes appear.

- [ ] **Step 3: Commit any final touch-ups (if needed)**

```bash
git add -A
git commit -m "chore(backend): foundation complete — full suite green"
```

---

## Self-Review notes (coverage check)

- **Auth/comptes** → Tasks 3, 5, 7, 8, 9 (User model, hashing/JWT, register, login, /me).
- **Profil apprenant** → Tasks 10, 11.
- **Sessions** → Tasks 12, 14.
- **Quotas** → Tasks 13, 14 (`quota.py` + enforced in `/sessions/start`, recorded in `/end`).
- **Jetons éphémères LiveKit** → Tasks 13, 14 (`livekit.py` + returned by `/sessions/start`, TTL from config).
- **Sécurité (pas de clé API côté client)** → backend mints tokens; LiveKit secret stays server-side in `config.py`.
- **Tests** → every endpoint and the quota/token logic covered (TDD throughout).

Out of scope for this sub-project (later plans): the LiveKit Agent itself (sub-project 2), debrief/pronunciation/memory services (3-5), Flutter app (6), billing/Stripe (7). The `errors`, `pronunciation_scores`, `fluency_metrics`, and `conversation_memory` tables are introduced with their owning services.
```
