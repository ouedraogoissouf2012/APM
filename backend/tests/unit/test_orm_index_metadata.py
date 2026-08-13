"""#306: three indexes exist in migrations (1a2b3c4d5e6f, c1d2e3f4a5b6) but were
missing from the ORM metadata (no `index=True` / `__table_args__` on the mapped
columns) — a future `alembic revision --autogenerate` diffing the ORM models
against the database would see them as extraneous and generate a migration that
DROPs them.

tests/conftest.py's `_setup_db` builds the whole test schema from
`Base.metadata.create_all` (no alembic involved) — so this reflects the actual
Postgres test database it produces and proves `create_all` now reproduces all
three indexes with the EXACT names the migrations already use in production.

The voice_consents test below (#360) is the same class of drift caught the
other way around: the ORM previously declared a SINGLE unique index
(`unique=True, index=True` on one column) where the migration
(d4e5f6a7b8c9) actually creates TWO distinct index objects — a named unique
constraint plus a separate non-unique index. An autogenerate diff would have
tried to drop one and create the other. The model was aligned to the
migration rather than the other way around, since the migration is what is
live in production.
"""

import pytest
from sqlalchemy import inspect


def _reflect_indexes(sync_conn, table_name: str) -> dict[str, dict]:
    inspector = inspect(sync_conn)
    return {ix["name"]: ix for ix in inspector.get_indexes(table_name)}


@pytest.mark.asyncio
async def test_create_all_reproduces_refresh_tokens_expires_at_index(_engine, _setup_db):
    async with _engine.connect() as conn:
        indexes = await conn.run_sync(_reflect_indexes, "refresh_tokens")

    assert "ix_refresh_tokens_expires_at" in indexes
    assert indexes["ix_refresh_tokens_expires_at"]["column_names"] == ["expires_at"]
    assert indexes["ix_refresh_tokens_expires_at"]["unique"] is False


@pytest.mark.asyncio
async def test_create_all_reproduces_idempotency_keys_created_at_index(_engine, _setup_db):
    async with _engine.connect() as conn:
        indexes = await conn.run_sync(_reflect_indexes, "idempotency_keys")

    assert "ix_idempotency_keys_created_at" in indexes
    assert indexes["ix_idempotency_keys_created_at"]["column_names"] == ["created_at"]
    assert indexes["ix_idempotency_keys_created_at"]["unique"] is False


@pytest.mark.asyncio
async def test_create_all_reproduces_users_email_lower_functional_unique_index(_engine, _setup_db):
    async with _engine.connect() as conn:
        indexes = await conn.run_sync(_reflect_indexes, "users")

    assert "uq_users_email_lower" in indexes
    index = indexes["uq_users_email_lower"]
    assert index["unique"] is True
    # A functional index has no plain column name — Postgres reflection surfaces
    # it as `None` in column_names with the expression in `expressions` instead
    # (or the raw DDL, depending on SQLAlchemy version). Either way this must NOT
    # be a plain index on the raw `email` column (that's the pre-existing
    # `ix_users_email`, a different index) — it must be the case-insensitive one.
    assert index["column_names"] == [None]


@pytest.mark.asyncio
async def test_create_all_reproduces_both_voice_consent_user_id_indexes(_engine, _setup_db):
    async with _engine.connect() as conn:
        indexes = await conn.run_sync(_reflect_indexes, "voice_consents")

    # The named UniqueConstraint from the migration (backs uq-per-user)...
    assert "uq_voice_consent_user" in indexes
    assert indexes["uq_voice_consent_user"]["unique"] is True
    assert indexes["uq_voice_consent_user"]["column_names"] == ["user_id"]
    # ...AND the separate, non-unique index the migration also creates. Both
    # must exist as distinct objects, matching what create_table produced in
    # production — not collapsed into the single unique index that
    # `mapped_column(unique=True, index=True)` would generate.
    assert "ix_voice_consents_user_id" in indexes
    assert indexes["ix_voice_consents_user_id"]["unique"] is False
    assert indexes["ix_voice_consents_user_id"]["column_names"] == ["user_id"]
