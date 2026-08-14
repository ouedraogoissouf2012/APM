"""Shared Postgres persistence idioms (#371).

Two invariants were independently copy-pasted into a 2nd feature repository
each (review/debrief for the lock, profile/voice_consent for the upsert) —
centralised here so a 3rd copy, or a future hardening of either idiom, has one
place to live instead of risking silent drift between features.
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession


async def advisory_xact_lock(session: AsyncSession, namespace: str, key: int) -> None:
    """Acquire a Postgres transaction-scoped advisory lock keyed on `key`,
    namespaced by a fixed hash of `namespace` so this can never collide with an
    unrelated advisory lock elsewhere keyed by a raw id from a different table
    (e.g. "review" vs "debrief" both locking on a plain integer id). Auto-released
    at commit/rollback — callers hold it for a read-compute-write section that
    must not interleave across two concurrent calls for the same key."""
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(namespace), key)))


async def first_touch_by_user_id(session: AsyncSession, model: type[Any], user_id: int) -> Any:
    """Atomic first-touch: INSERT ... ON CONFLICT DO NOTHING on `user_id`, then
    read the row back. A plain get-then-create races two concurrent first
    requests for the SAME new user (e.g. two devices onboarding) into a double
    INSERT that trips a unique/primary-key constraint — one 500. Here the
    loser's insert is a no-op and both read the same row.

    `model` must declare a `user_id` column carrying a unique or primary-key
    constraint — NOT necessarily its primary key (e.g. VoiceConsent's PK is
    `id`; LearnerProfile's PK IS `user_id`). The reread below matches on the
    column, not the PK, so it works for both shapes. Untyped (`Any` in, `Any`
    out) rather than a generic TypeVar: `model.user_id` is a dynamic lookup no
    common base guarantees (VoiceConsent/LearnerProfile share no such base),
    and every caller already re-asserts the concrete type via its own return
    annotation, so a Protocol here would add indirection without adding
    safety."""
    await session.execute(
        pg_insert(model).values(user_id=user_id).on_conflict_do_nothing(index_elements=["user_id"])
    )
    await session.commit()
    row = await session.scalar(select(model).where(model.user_id == user_id))
    assert row is not None  # just inserted by us, or already present
    return row
