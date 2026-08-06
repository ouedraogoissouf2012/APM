from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AnalyticsEventRow(Base):
    """Append-only product-analytics event (#129). No transcript content or PII —
    only a name, the pseudonymous user id, and structured properties."""

    __tablename__ = "analytics_events"
    # Exactly-once ACTIVATION per user, enforced at the DB (not by a racy count):
    # a partial unique index so a cross-session race inserts at most one activation
    # (the loser's commit fails and is swallowed by the best-effort analytics path).
    __table_args__ = (
        Index(
            "uq_analytics_activation_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("name = 'activation'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    properties: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
