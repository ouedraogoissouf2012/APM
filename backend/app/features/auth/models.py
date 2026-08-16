from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, func
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
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    # Case-insensitive uniqueness backstop for the lowercase-email canonicalisation
    # (#220): the app already lowercases on register/login, but this is what
    # actually stops 'Jean@x.com' and 'jean@x.com' from coexisting. Matches the
    # functional index already created by migration c1d2e3f4a5b6 EXACTLY (name +
    # expression) — this is metadata alignment only, no new migration (#306). Must
    # come AFTER `email` is defined: `__table_args__` is evaluated as a normal
    # class-body statement, so it needs `email` already bound in this scope.
    __table_args__ = (Index("uq_users_email_lower", func.lower(email), unique=True),)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    native_language: Mapped[str] = mapped_column(String(8), default="fr", nullable=False)
    cefr_level: Mapped[str] = mapped_column(String(2), default="A1", nullable=False)
    tier: Mapped[str] = mapped_column(String(16), default=TIER_FREE, nullable=False)
    # Grants access to admin-only endpoints (e.g. changing a user's tier). NEVER
    # settable through the API — an attacker who could would self-promote. Set it
    # in the database (or a CLI) to bootstrap the first admin.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Lets an admin suspend a compromised/abusive account WITHOUT a destructive
    # DELETE (#232): a deactivated user can neither authenticate nor refresh.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

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

    # One-shot password reset (#449). Hash only; raw token never stored.
    reset_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    reset_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Only the SHA-256 hash is stored — never the raw token.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    # Indexed (#306): the periodic purge task (#271) filters by expires_at; without
    # this the ORM metadata drifts from the index migration 1a2b3c4d5e6f already
    # created, so a future autogenerate would DROP it.
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
