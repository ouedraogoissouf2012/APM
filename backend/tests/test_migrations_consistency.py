"""Guard that the Alembic migrations match the ORM models and stay linear (#398).

Everywhere else the test schema is built by ``Base.metadata.create_all`` (conftest),
NEVER by the migrations. So a model change shipped without a matching migration
passes CI while breaking the real, migration-built production schema — the exact
blind spot that produced the #306/#358/#360 index drifts. This module closes it by
running the MIGRATIONS against the test database and asserting:

1. exactly one head (a second head makes ``alembic upgrade head`` fail at deploy);
2. ``alembic upgrade head`` from an empty database yields a schema with NO
   autogenerate diff against the ORM metadata (missing column, wrong nullability,
   wrong type, missing/renamed index or constraint would all surface here);
3. a full ``downgrade base`` -> ``upgrade head`` round-trip runs clean (every
   migration is reversible).

These run in a subprocess against ``DATABASE_URL_TEST`` (a fresh Alembic process so
``env.py`` resolves the URL from our override with no cached-settings games), and
reset the public schema before and after so they never disturb the create_all suite.
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.registry import Base

_BACKEND = Path(__file__).resolve().parent.parent
_ALEMBIC_INI = _BACKEND / "alembic.ini"


def _alembic_config() -> Config:
    return Config(str(_ALEMBIC_INI))


def _run_alembic(*args: str, db_url: str) -> None:
    # Fresh Alembic CLI process: env.py reads DATABASE_URL via get_settings(), so a
    # subprocess override targets the test DB without monkeypatching cached settings
    # or fighting the running event loop.
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(_BACKEND),
        env={**os.environ, "DATABASE_URL": db_url},
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"`alembic {' '.join(args)}` failed (exit {proc.returncode}).\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )


async def _reset_public_schema(db_url: str) -> None:
    engine = create_async_engine(db_url, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.execute(sa.text("DROP SCHEMA public CASCADE"))
            await conn.execute(sa.text("CREATE SCHEMA public"))
    finally:
        await engine.dispose()


def _compare(sync_conn) -> list:
    # compare_type=True catches the drift classes that have actually bitten us —
    # missing/extra columns, wrong type, wrong nullability, and missing/renamed
    # indexes & constraints (#306/#358/#360 were index drifts).
    # compare_server_default is deliberately OFF: several migrations set a
    # server_default purely to backfill a value when adding a NOT NULL column,
    # while the model intentionally does not declare one (the app always supplies
    # the value). compare_server_default flags every such intentional divergence as
    # a false "modify_default", which would make this guard permanently red.
    ctx = MigrationContext.configure(sync_conn, opts={"compare_type": True})
    return compare_metadata(ctx, Base.metadata)


async def _autogenerate_diff(db_url: str) -> list:
    engine = create_async_engine(db_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            return await conn.run_sync(_compare)
    finally:
        await engine.dispose()


def _is_noise(diff) -> bool:
    # Alembic's own bookkeeping table lives in the DB but not in Base.metadata, so
    # compare_metadata always reports it as an extra table — not real model drift.
    return "alembic_version" in repr(diff)


def test_exactly_one_alembic_head() -> None:
    heads = ScriptDirectory.from_config(_alembic_config()).get_heads()
    assert len(heads) == 1, (
        f"expected exactly one Alembic head, found {len(heads)}: {heads}. "
        "Two heads make `alembic upgrade head` fail at deploy — merge them with a "
        "merge migration."
    )


def test_migrations_match_models_and_round_trip() -> None:
    db_url = get_settings().database_url_test
    assert db_url, "DATABASE_URL_TEST must be set for the migration consistency test"
    try:
        asyncio.run(_reset_public_schema(db_url))
        _run_alembic("upgrade", "head", db_url=db_url)

        drift = [d for d in asyncio.run(_autogenerate_diff(db_url)) if not _is_noise(d)]
        assert drift == [], (
            "The ORM models and the Alembic migrations have diverged — `alembic "
            "upgrade head` from empty does not reproduce Base.metadata. A model was "
            "likely changed without a matching migration. Diff:\n"
            + "\n".join(repr(d) for d in drift)
        )

        # Every migration must be reversible: full down then back up, clean.
        _run_alembic("downgrade", "base", db_url=db_url)
        _run_alembic("upgrade", "head", db_url=db_url)
    finally:
        # Leave the DB clean so the create_all suite starts from a fresh schema.
        asyncio.run(_reset_public_schema(db_url))
