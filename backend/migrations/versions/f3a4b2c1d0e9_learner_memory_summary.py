"""learner memory summary

Revision ID: f3a4b2c1d0e9
Revises: ba64d112828d
Create Date: 2026-07-02 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "f3a4b2c1d0e9"
down_revision = "ba64d112828d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "learner_profiles",
        sa.Column("memory_summary", sa.Text(), nullable=False, server_default=""),
    )
    op.alter_column("learner_profiles", "memory_summary", server_default=None)


def downgrade() -> None:
    op.drop_column("learner_profiles", "memory_summary")
