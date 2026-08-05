from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class VoiceConsent(Base):
    """Per-user voice consent record (#128). Protective by default: transcription
    is ON so the app works out of the box (the audio is ephemeral — processed
    then discarded, never stored), but every consent is revocable. Scoring, B2B
    sharing and model training are OFF by default — strict opt-in.
    `updated_at` timestamps the record so a change is auditable/versioned."""

    __tablename__ = "voice_consents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    # Uploading audio to the server STT (Groq). ON by default; revoking it means
    # the client must fall back to on-device recognition.
    transcription: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Pronunciation/fluency scoring (#111). OFF until explicitly granted.
    scoring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Sharing voice-derived results with a school/employer. OFF; explicit choice.
    b2b_share: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Using the learner's data to train models. OFF; distinct, revocable opt-in.
    model_training: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
