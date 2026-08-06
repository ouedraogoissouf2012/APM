"""idempotency: nullable response for claim-first atomicity (#185)

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-06 00:00:00.000000

A NULL response now means the key is CLAIMED but the work is still in flight;
a non-NULL response means the work completed and its result is cached. This lets
run_once claim the key atomically BEFORE doing the work, so concurrent replays of
the same key cannot both process the turn.
"""

import sqlalchemy as sa
from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the "" default and allow NULL (the "claimed/pending" sentinel).
    op.alter_column(
        "idempotency_keys",
        "response",
        existing_type=sa.Text(),
        nullable=True,
        server_default=None,
    )


def downgrade() -> None:
    # Backfill any pending NULLs to "" before restoring NOT NULL.
    op.execute("UPDATE idempotency_keys SET response = '' WHERE response IS NULL")
    op.alter_column(
        "idempotency_keys",
        "response",
        existing_type=sa.Text(),
        nullable=False,
        server_default="",
    )
