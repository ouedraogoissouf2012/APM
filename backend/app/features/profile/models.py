from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LearnerProfile(Base):
    __tablename__ = "learner_profiles"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    interests: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    goal: Mapped[str | None] = mapped_column(String(500), nullable=True)
    correction_intensity: Mapped[str] = mapped_column(String(16), default="gentle", nullable=False)
    accent: Mapped[str] = mapped_column(String(8), default="us", nullable=False)
