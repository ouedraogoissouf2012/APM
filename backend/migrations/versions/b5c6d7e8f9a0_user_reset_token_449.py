"""users: password-reset token columns (#449)

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-08-16 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "b5c6d7e8f9a0"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("reset_token_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "users", sa.Column("reset_token_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index("uq_users_reset_token_hash", "users", ["reset_token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_users_reset_token_hash", table_name="users")
    op.drop_column("users", "reset_token_expires_at")
    op.drop_column("users", "reset_token_hash")
