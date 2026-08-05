"""review items — spaced repetition of recurring error types (#117)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-05 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("error_type", sa.String(length=40), nullable=False),
        sa.Column("latest_correction", sa.Text(), server_default="", nullable=False),
        sa.Column("stage", sa.Integer(), server_default="0", nullable=False),
        sa.Column("clean_streak", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="due", nullable=False),
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "error_type", name="uq_review_user_error_type"),
    )
    op.create_index("ix_review_items_user_id", "review_items", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_review_items_user_id", table_name="review_items")
    op.drop_table("review_items")
