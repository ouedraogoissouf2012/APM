"""#371: app/core/persistence.py centralises the advisory-lock namespacing and
insert-ignore-reread idiom previously duplicated in review/debrief (lock) and
profile/voice_consent (upsert). Unit-tested here with fake/substitute sessions —
these statements are pure SQLAlchemy Core construction, so proving their shape
doesn't need a live Postgres; the actual race-safety these functions protect is
already proven end-to-end by the real-DB concurrency tests in test_review_api.py
/ test_voice_consent_api.py / test_profile.py / test_debrief_api.py, which stay
green through the repositories now delegating to these helpers.
"""

import pytest
from sqlalchemy import Integer
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.persistence import advisory_xact_lock, first_touch_by_user_id


class _TestBase(DeclarativeBase):
    """Isolated from app.database.Base so these fixture models never leak into
    the real schema created/dropped by the DB-backed test fixtures."""


class _UserIdIsPk(_TestBase):
    """Mirrors LearnerProfile's shape: user_id IS the primary key."""

    __tablename__ = "_test_persistence_user_id_is_pk"
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)


class _UserIdIsNotPk(_TestBase):
    """Mirrors VoiceConsent's shape: a separate `id` PK, user_id a plain
    column — proves the reread matches on user_id, not the PK."""

    __tablename__ = "_test_persistence_user_id_is_not_pk"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer)


def _compiled(stmt) -> str:
    # The postgres dialect explicitly: ON CONFLICT is postgres-specific and the
    # default/generic compiler doesn't know how to render it.
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


class _FakeLockSession:
    def __init__(self) -> None:
        self.executed: list = []

    async def execute(self, stmt):
        self.executed.append(stmt)


@pytest.mark.asyncio
async def test_advisory_xact_lock_locks_on_hashtext_of_namespace_and_the_key():
    session = _FakeLockSession()

    await advisory_xact_lock(session, "review", 42)

    assert len(session.executed) == 1
    sql = _compiled(session.executed[0])
    assert "pg_advisory_xact_lock" in sql
    assert "hashtext" in sql
    assert "review" in sql
    assert "42" in sql


@pytest.mark.asyncio
async def test_advisory_xact_lock_different_namespaces_compile_differently():
    # Guards against a hardcoded/ignored namespace argument: two different
    # namespaces for the SAME key must produce different SQL text, or they'd
    # collide on the same lock despite being unrelated features.
    session = _FakeLockSession()

    await advisory_xact_lock(session, "review", 1)
    await advisory_xact_lock(session, "debrief", 1)

    review_sql, debrief_sql = (_compiled(stmt) for stmt in session.executed)
    assert review_sql != debrief_sql


class _FakeUpsertSession:
    def __init__(self, existing=None) -> None:
        self.executed: list = []
        self.committed = False
        self._existing = existing

    async def execute(self, stmt):
        self.executed.append(stmt)

    async def commit(self):
        self.committed = True

    async def scalar(self, stmt):
        self.executed.append(stmt)
        return self._existing


@pytest.mark.asyncio
async def test_first_touch_inserts_commits_then_rereads_and_returns_the_row():
    existing = _UserIdIsPk(user_id=7)
    session = _FakeUpsertSession(existing=existing)

    result = await first_touch_by_user_id(session, _UserIdIsPk, 7)

    assert result is existing
    assert session.committed is True
    assert len(session.executed) == 2  # insert, then the reread select
    insert_sql = _compiled(session.executed[0])
    assert "INSERT" in insert_sql.upper()
    assert "ON CONFLICT" in insert_sql.upper()
    assert "DO NOTHING" in insert_sql.upper()
    assert "user_id" in insert_sql


@pytest.mark.asyncio
async def test_first_touch_reread_matches_on_user_id_not_the_primary_key():
    # VoiceConsent's shape: PK is `id`, user_id is a separate column. The
    # reread must filter on user_id, not assume it's the PK (a `.get()` reread
    # would look up the wrong row — or raise — here).
    existing = _UserIdIsNotPk(id=1, user_id=99)
    session = _FakeUpsertSession(existing=existing)

    result = await first_touch_by_user_id(session, _UserIdIsNotPk, 99)

    assert result is existing
    reread_sql = _compiled(session.executed[-1])
    assert "user_id" in reread_sql
    assert "99" in reread_sql


@pytest.mark.asyncio
async def test_first_touch_raises_if_the_reread_finds_nothing():
    # The insert-then-reread invariant: if neither our insert nor a concurrent
    # winner's left a row behind, that's a bug (e.g. a missing unique
    # constraint on user_id) — must fail loudly, never return None silently.
    session = _FakeUpsertSession(existing=None)

    with pytest.raises(AssertionError):
        await first_touch_by_user_id(session, _UserIdIsPk, 7)
