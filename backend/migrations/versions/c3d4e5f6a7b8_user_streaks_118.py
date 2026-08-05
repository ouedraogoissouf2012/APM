"""user streaks + weekly goal (#118)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-05 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("current_streak", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("longest_streak", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("users", sa.Column("last_active_date", sa.Date(), nullable=True))
    op.add_column(
        "users",
        sa.Column("weekly_goal_minutes", sa.Integer(), server_default="30", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "weekly_goal_minutes")
    op.drop_column("users", "last_active_date")
    op.drop_column("users", "longest_streak")
    op.drop_column("users", "current_streak")
