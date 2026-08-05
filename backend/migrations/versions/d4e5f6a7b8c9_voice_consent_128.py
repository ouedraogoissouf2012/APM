"""voice consent — protective-by-default, revocable (#128)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-05 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_consents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("transcription", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("scoring", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("b2b_share", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("model_training", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", name="uq_voice_consent_user"),
    )
    op.create_index("ix_voice_consents_user_id", "voice_consents", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_voice_consents_user_id", table_name="voice_consents")
    op.drop_table("voice_consents")
