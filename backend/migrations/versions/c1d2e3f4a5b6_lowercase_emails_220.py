"""auth: canonicalise emails to lowercase + case-insensitive unique index (#220)

Revision ID: c1d2e3f4a5b6
Revises: b8c9d0e1f2a3
Create Date: 2026-08-10 00:00:00.000000

Emails are case-insensitive in practice, but `users.email` was unique
case-SENSITIVELY and neither register nor login normalised — so 'Jean@x.com' and
'jean@x.com' were two accounts, and a phone's auto-capitalisation could 401 a
learner with the right password (#220). This lowercases existing addresses and
adds a functional UNIQUE index on lower(email) as the DB-level guard.

Non-destructive by choice: if two accounts differ ONLY by case, the UPDATE (or the
unique index build) fails loudly on the duplicate. Merging such accounts is a
human decision (whose progress to keep), so it is NOT auto-deleted here — resolve
the duplicate by hand, then re-run. On a fresh/empty database (CI) this is a no-op
beyond creating the index.
"""

import sqlalchemy as sa
from alembic import op

revision = "c1d2e3f4a5b6"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None

_INDEX = "uq_users_email_lower"


def upgrade() -> None:
    op.execute("UPDATE users SET email = lower(email) WHERE email <> lower(email)")
    op.create_index(_INDEX, "users", [sa.text("lower(email)")], unique=True)


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="users")
