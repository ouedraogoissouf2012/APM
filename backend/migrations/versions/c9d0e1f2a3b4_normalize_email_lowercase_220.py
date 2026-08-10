"""normalize emails to lowercase + case-insensitive unique index (#220)

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-08-10

Emails are now normalized to lowercase at the auth boundary. This migration
brings existing data and the schema in line:

  1. Lowercase every stored email so it matches the new invariant.
  2. Replace the case-sensitive unique index on ``email`` with
       - a plain (non-unique) index for equality lookups, and
       - a functional UNIQUE index on ``lower(email)`` enforcing
         case-insensitive uniqueness as a DB-level safety net.

If pre-existing rows collide only by case (e.g. ``A@x`` and ``a@x``), step 1
makes them identical and creating the unique index fails loudly — intended: a
human must merge/resolve genuine duplicate accounts rather than silently losing
data. Not expected at the app's current stage, but surfaced instead of hidden.
"""

import sqlalchemy as sa
from alembic import op

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE users SET email = lower(email) WHERE email <> lower(email)")
    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_index("ix_users_email_lower", "users", [sa.text("lower(email)")], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_email_lower", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=True)
