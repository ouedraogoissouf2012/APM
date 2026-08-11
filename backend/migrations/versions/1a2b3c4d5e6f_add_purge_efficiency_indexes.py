"""Add indexes for purge efficiency (expires_at, created_at)

Addresses #271: The purge task (#278) filters by expires_at and created_at
without indexes, causing seq-scans. This migration adds indexes to make
TTL cleanup efficient (DELETE with WHERE on expires_at/created_at).

Revision ID: 1a2b3c4d5e6f
Revises: d2e3f4a5b6c7
Create Date: 2026-08-11 13:30:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "1a2b3c4d5e6f"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add index on refresh_tokens.expires_at for efficient TTL purge
    op.create_index(
        "ix_refresh_tokens_expires_at",
        "refresh_tokens",
        ["expires_at"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    # Add index on refresh_tokens.created_at for potential time-range queries
    op.create_index(
        "ix_refresh_tokens_created_at",
        "refresh_tokens",
        ["created_at"],
    )
    # Add index on idempotency_keys.created_at for efficient TTL purge
    op.create_index(
        "ix_idempotency_keys_created_at",
        "idempotency_keys",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_idempotency_keys_created_at", table_name="idempotency_keys")
    op.drop_index("ix_refresh_tokens_created_at", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_expires_at", table_name="refresh_tokens")
