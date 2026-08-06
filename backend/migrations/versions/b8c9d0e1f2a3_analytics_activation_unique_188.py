"""analytics: exactly-once activation per user (partial unique index) (#188)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-08-06 00:00:00.000000

Enforces at the DB what a racy count could not: at most one `activation` event per
user. A partial unique index on (user_id) WHERE name = 'activation' means a
cross-session race inserts at most one activation (the loser's commit fails and is
swallowed by the best-effort analytics path). Other event names are unaffected.
"""

import sqlalchemy as sa
from alembic import op

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None

_INDEX = "uq_analytics_activation_per_user"


def upgrade() -> None:
    # The old count-based path could double-emit under a race; drop any existing
    # duplicate activations (keep the earliest id) before enforcing uniqueness.
    op.execute(
        """
        DELETE FROM analytics_events a
        USING analytics_events b
        WHERE a.name = 'activation'
          AND b.name = 'activation'
          AND a.user_id = b.user_id
          AND a.id > b.id
        """
    )
    op.create_index(
        _INDEX,
        "analytics_events",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("name = 'activation'"),
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="analytics_events")
