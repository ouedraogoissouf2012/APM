"""sessions: at most one active session per user (#428)

Revision ID: a4b5c6d7e8f9
Revises: 22c153382454
Create Date: 2026-08-16 00:00:00.000000

The "one active session" invariant lived only in SessionService.start() +
User.lock. A script or a future endpoint that skipped the lock could insert a
second ended_at IS NULL row; get_active_for_user then returned an arbitrary one.

Close extras (keep the most recently started) then add a partial unique index.
"""

import sqlalchemy as sa
from alembic import op

revision = "a4b5c6d7e8f9"
down_revision = "22c153382454"
branch_labels = None
depends_on = None

_INDEX = "uq_sessions_one_active_per_user"


def upgrade() -> None:
    op.execute(
        """
        UPDATE sessions AS extra
        SET ended_at = NOW(),
            duration_minutes = GREATEST(
                0.0,
                EXTRACT(EPOCH FROM (NOW() - extra.started_at)) / 60.0
            )
        FROM sessions AS keeper
        WHERE extra.ended_at IS NULL
          AND keeper.ended_at IS NULL
          AND extra.user_id = keeper.user_id
          AND (
              extra.started_at < keeper.started_at
              OR (extra.started_at = keeper.started_at AND extra.id < keeper.id)
          )
        """
    )
    op.create_index(
        _INDEX,
        "sessions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="sessions")
