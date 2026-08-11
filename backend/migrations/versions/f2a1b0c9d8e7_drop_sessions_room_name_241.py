"""drop sessions.room_name (LiveKit removal, #241)

The ``room_name`` column only ever fed the LiveKit room-join token. With LiveKit
removed (it was issued on every /sessions/start but never consumed by the mobile
client, which reads only ``session_id``), the column is dead. Dropping it also
drops its UNIQUE constraint (Postgres removes constraints dependent on the column).

Downgrade re-adds the column and its unique constraint, but cannot reconstruct the
per-session UUID room names — so it only succeeds on an empty ``sessions`` table.

Revision ID: f2a1b0c9d8e7
Revises: 1a2b3c4d5e6f
"""

import sqlalchemy as sa
from alembic import op

revision = "f2a1b0c9d8e7"
down_revision = "1a2b3c4d5e6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("sessions", "room_name")


def downgrade() -> None:
    op.add_column("sessions", sa.Column("room_name", sa.String(length=80), nullable=False))
    op.create_unique_constraint("sessions_room_name_key", "sessions", ["room_name"])
