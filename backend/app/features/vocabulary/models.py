from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Review status of a vocabulary entry. "review" = still learning (default),
# "known" = the learner tapped "Je le sais". The spaced-repetition scheduling
# (#117) builds on this status; here we only store it.
STATUS_REVIEW = "review"
STATUS_KNOWN = "known"


class VocabularyEntry(Base):
    __tablename__ = "vocabulary_entries"
    # One card per (user, word): re-seeing a word updates the same entry instead
    # of piling duplicates in the notebook.
    __table_args__ = (UniqueConstraint("user_id", "word", name="uq_vocabulary_user_word"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # The session it was first captured in — powers the "VU EN SESSION #23" overline.
    session_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    word: Mapped[str] = mapped_column(String(120), nullable=False)
    phonetic: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    translation: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    # The learner's actual sentence the word appeared in.
    example: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=STATUS_REVIEW, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
