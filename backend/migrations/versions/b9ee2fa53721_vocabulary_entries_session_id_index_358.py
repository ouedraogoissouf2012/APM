"""vocabulary_entries: index session_id (#358)

vocabulary_entries.session_id (FK SET NULL to sessions.id) had no index: the
"VU EN SESSION #23" lookup and the FK's own SET NULL cascade on session
deletion both scan session_id, and an unindexed FK column forces a sequential
scan of vocabulary_entries as it grows. Mirrors sessions.mission_id, already
indexed for the identical FK-lookup reason.

Revision ID: b9ee2fa53721
Revises: eea2e957ec48
Create Date: 2026-08-13 00:00:00.000000
"""

from alembic import op

revision = "b9ee2fa53721"
down_revision = "eea2e957ec48"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_vocabulary_entries_session_id", "vocabulary_entries", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_vocabulary_entries_session_id", table_name="vocabulary_entries")
