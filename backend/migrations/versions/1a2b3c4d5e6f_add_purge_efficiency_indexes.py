"""Add indexes for purge efficiency (#271)

The periodic purge task (#278) filters refresh_tokens by expires_at and
idempotency_keys by created_at with no index, causing seq-scans. This migration
adds those two indexes so the TTL cleanup is index-driven.

Notes:
- analytics_events.created_at is ALREADY indexed (migration #129), so no index is
  added for it here.
- The refresh_tokens purge deletes ALL expired tokens (`WHERE expires_at < now`),
  revoked or not, so this is a FULL index — a partial `WHERE revoked_at IS NULL`
  index could not serve that query.

Revision ID: 1a2b3c4d5e6f
Revises: d2e3f4a5b6c7
Create Date: 2026-08-11 13:30:00.000000
"""

from alembic import op

revision = "1a2b3c4d5e6f"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_refresh_tokens_expires_at",
        "refresh_tokens",
        ["expires_at"],
    )
    op.create_index(
        "ix_idempotency_keys_created_at",
        "idempotency_keys",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_idempotency_keys_created_at", table_name="idempotency_keys")
    op.drop_index("ix_refresh_tokens_expires_at", table_name="refresh_tokens")
