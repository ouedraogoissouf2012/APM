from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Spaced-repetition status of a recurring error type for one learner.
# "due"       = scheduled for review (its next_review_at has arrived or will).
# "mastered"  = not seen for MASTERY_STREAK consecutive sessions; no longer surfaced.
STATUS_DUE = "due"
STATUS_MASTERED = "mastered"


class ReviewItem(Base):
    __tablename__ = "review_items"
    # One SRS item per (user, error_type): a type re-appearing updates its schedule
    # instead of creating a second row.
    __table_args__ = (UniqueConstraint("user_id", "error_type", name="uq_review_user_error_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    error_type: Mapped[str] = mapped_column(String(40), nullable=False)
    # The most recent correction seen for this type, shown as the review example.
    latest_correction: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # SRS stage: index into the J+1/J+3/J+7 interval ladder (0,1,2).
    stage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Consecutive sessions WITHOUT this error type; MASTERY_STREAK -> mastered.
    clean_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=STATUS_DUE, nullable=False)
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
