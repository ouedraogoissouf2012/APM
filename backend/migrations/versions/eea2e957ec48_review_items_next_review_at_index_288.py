"""review_items: composite (user_id, next_review_at) index (#288)

#288 flagged next_review_at as unindexed for list_due (repository.py), which
filters by user_id, status, and next_review_at (NULL or <= now), ordered by
next_review_at. This replaces the single-column ix_review_items_user_id index
with a composite (user_id, next_review_at) index: it still serves
list_for_user's plain user_id lookup (used on every session-end upsert) as a
leftmost-prefix match, while adding index coverage for next_review_at. A bare
next_review_at-only index was rejected — every query on this table is
user_id-scoped first, so it would go unused.

Measured impact (EXPLAIN ANALYZE against a scratch DB seeded with 30k users x
16 rows = 480k review_items rows, matching the taxonomy's per-user cap in
error_taxonomy.py): list_due already got an efficient Index Scan via the
PRE-EXISTING single-column user_id index (deployed since #117, before this
issue was filed) — sub-millisecond, no full table scan, growing or not.
Rows per user are hard-capped at len(CANONICAL_ERROR_TYPES) = 16 by the
taxonomy, so #288's "full table scan on a growing table" premise does not
hold today; both the old and new index produce the same Index Scan + Sort
plan for list_due at this row count (the ORDER BY ... NULLS FIRST needs a
Sort node either way — a plain ascending b-tree index is NULLS LAST — but
sorting <=16 rows is free).

This migration still closes the literal audit gap and merges two indexing
needs into one (no added write-maintenance cost vs. a second index), but is
preventive rather than an active-bug fix: it becomes load-bearing only if the
taxonomy's per-user cap is ever lifted (error_taxonomy.py notes a future
ERRANT-based replacement for the normalizer).

Revision ID: eea2e957ec48
Revises: f2a1b0c9d8e7
Create Date: 2026-08-12 00:00:00.000000
"""

from alembic import op

revision = "eea2e957ec48"
down_revision = "f2a1b0c9d8e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_review_items_user_id", table_name="review_items")
    op.create_index(
        "ix_review_items_user_id_next_review_at",
        "review_items",
        ["user_id", "next_review_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_review_items_user_id_next_review_at", table_name="review_items")
    op.create_index("ix_review_items_user_id", "review_items", ["user_id"])
