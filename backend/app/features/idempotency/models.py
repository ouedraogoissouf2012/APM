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
    # The stored response to replay verbatim. For a turn it's the reply text.
    response: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
