from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class VoiceConsent(Base):
    """Per-user voice consent record (#128). Protective by default: transcription
    is ON so the app works out of the box (the audio is ephemeral — processed
    then discarded, never stored), but every consent is revocable. Scoring, B2B
    sharing and model training are OFF by default — strict opt-in.
    `updated_at` timestamps the record so a change is auditable/versioned."""

    __tablename__ = "voice_consents"
    # Mirrors the live migration (d4e5f6a7b8c9) exactly: a named UniqueConstraint
    # backing the one-consent-per-user invariant, PLUS a separate non-unique
    # index on the same column — two distinct index objects in Postgres, not
    # the single unique index `mapped_column(unique=True, index=True)` would
    # produce (#360: that drift would make an autogenerate diff try to DROP one
    # of the two and CREATE the other).
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_voice_consent_user"),
        Index("ix_voice_consents_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Uploading audio to the server STT (Groq). ON by default; revoking it means
    # the client must fall back to on-device recognition. server_default mirrors the
    # migration so an INSERT that omits the column (a Core upsert, or a raw insert)
    # gets the protective default at the DB — not just via the ORM Python default.
    transcription: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    # Pronunciation/fluency scoring (#111). OFF until explicitly granted.
    scoring: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    # Sharing voice-derived results with a school/employer. OFF; explicit choice.
    b2b_share: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    # Using the learner's data to train models. OFF; distinct, revocable opt-in.
    model_training: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
