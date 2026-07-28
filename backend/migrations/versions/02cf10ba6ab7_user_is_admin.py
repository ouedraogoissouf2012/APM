"""user_is_admin

Revision ID: 02cf10ba6ab7
Revises: fb4423db1c92
Create Date: 2026-07-28 12:58:55.467353
"""

import sqlalchemy as sa
from alembic import op

revision = "02cf10ba6ab7"
down_revision = "fb4423db1c92"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default backfills existing rows to false, then is removed so the app
    # (not the DB) owns the default going forward — same pattern as memory_summary.
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("users", "is_admin", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "is_admin")
