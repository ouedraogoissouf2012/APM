"""sessions: composite (user_id, started_at) index (#359)

sessions had only a single-column ix_sessions_user_id index. Two query shapes
run against this table: get_active_for_user (repository.py) filters by
user_id + ended_at IS NULL, and list_recent_for_user filters by user_id and
orders by started_at DESC, id DESC (the history feed). The single-column
index served the filter but not the ORDER BY, forcing a Sort node once a
user's row count grows past what fits a quick in-memory sort.

Replaces ix_sessions_user_id with a composite (user_id, started_at) index, on
the model of #288 (review_items): the composite still serves the plain
user_id filter as a leftmost-prefix match (so get_active_for_user is
unaffected), while list_recent_for_user's ORDER BY started_at DESC is now
satisfiable via a backward index scan (Postgres b-tree indexes are scannable
in both directions) instead of a Sort. One index instead of two also removes
write-amplification on every session insert/update.

Revision ID: 22c153382454
Revises: b9ee2fa53721
Create Date: 2026-08-13 00:00:00.000000
"""

from alembic import op

revision = "22c153382454"
down_revision = "b9ee2fa53721"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.create_index("ix_sessions_user_id_started_at", "sessions", ["user_id", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_sessions_user_id_started_at", table_name="sessions")
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
