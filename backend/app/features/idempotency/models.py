from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IdempotencyKey(Base):
    """Remembers the result of a processed request keyed by (user, key), so a
    client replaying a turn after a dropped connection (offline-first, #127) gets
    the SAME result without re-processing it — no duplicate turn, no double quota
    charge (#119)."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_idempotency_user_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # The client-supplied idempotency key (a UUID per queued turn).
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    # The stored response to replay verbatim. NULL means the key is CLAIMED but
    # the work is still running (a concurrent replay must wait, not re-process);
    # a non-NULL value is the completed, cacheable result (for a turn, the reply).
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Indexed (#306): the periodic purge task (#271) filters by created_at; without
    # this the ORM metadata drifts from the index migration 1a2b3c4d5e6f already
    # created, so a future autogenerate would DROP it.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
