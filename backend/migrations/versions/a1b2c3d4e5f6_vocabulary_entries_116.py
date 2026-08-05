"""vocabulary entries — "Mot du jour" notebook (#116)

Revision ID: a1b2c3d4e5f6
Revises: fc233850563a
Create Date: 2026-08-05 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "fc233850563a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vocabulary_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("word", sa.String(length=120), nullable=False),
        sa.Column("phonetic", sa.String(length=200), server_default="", nullable=False),
        sa.Column("translation", sa.String(length=300), server_default="", nullable=False),
        sa.Column("example", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="review", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "word", name="uq_vocabulary_user_word"),
    )
    op.create_index("ix_vocabulary_entries_user_id", "vocabulary_entries", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_vocabulary_entries_user_id", table_name="vocabulary_entries")
    op.drop_table("vocabulary_entries")
