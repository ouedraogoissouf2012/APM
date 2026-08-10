"""auth: is_active flag on users — suspend an account without a destructive delete (#232)

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-08-10 00:00:00.000000

Adds users.is_active (default true). A deactivated account can neither authenticate
nor refresh, so an admin can freeze a compromised/abusive user without DELETE (which
would cascade away all their data). Existing rows default to active via server_default.
"""

import sqlalchemy as sa
from alembic import op

revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("users", "is_active")
