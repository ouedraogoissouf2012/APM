from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    native_language: Mapped[str] = mapped_column(String(8), default="fr", nullable=False)
    cefr_level: Mapped[str] = mapped_column(String(2), default="A1", nullable=False)
    tier: Mapped[str] = mapped_column(String(16), default="free", nullable=False)

    # Daily quota tracking (reset when quota_date rolls over)
    quota_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    minutes_used_today: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
