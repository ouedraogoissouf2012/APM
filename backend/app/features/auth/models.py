from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.features.streaks.logic import DEFAULT_WEEKLY_GOAL_MINUTES

# User tiers. Single source for the quota logic and the model default; the paid
# tier is added here so no feature hunts string literals. "premium" lifts the
# daily-minutes quota (see app.core.quota.remaining_minutes).
TIER_FREE = "free"
TIER_PREMIUM = "premium"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    native_language: Mapped[str] = mapped_column(String(8), default="fr", nullable=False)
    cefr_level: Mapped[str] = mapped_column(String(2), default="A1", nullable=False)
    tier: Mapped[str] = mapped_column(String(16), default=TIER_FREE, nullable=False)
    # Grants access to admin-only endpoints (e.g. changing a user's tier). NEVER
    # settable through the API — an attacker who could would self-promote. Set it
    # in the database (or a CLI) to bootstrap the first admin.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Daily quota tracking (reset when quota_date rolls over)
    quota_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    minutes_used_today: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Habit tracking (#118): consecutive active days + weekly practice goal.
    current_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_active_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    weekly_goal_minutes: Mapped[int] = mapped_column(
        Integer, default=DEFAULT_WEEKLY_GOAL_MINUTES, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Case-insensitive uniqueness (issue #220). Emails are normalized to
    # lowercase at the auth write boundary; this functional UNIQUE index is the
    # DB-level safety net that also blocks case-variant duplicates from any code
    # path that might bypass normalization. The plain index on `email` above
    # serves equality lookups on the (already lowercased) stored value.
    __table_args__ = (Index("ix_users_email_lower", text("lower(email)"), unique=True),)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Only the SHA-256 hash is stored — never the raw token.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
