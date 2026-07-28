from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.engines import ENGINE_FAKE
from app.database import Base


class ConversationSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False)  # "scenario" | "free" | "mission"
    scenario_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Set when the session runs a compiled mission (mode="mission"); its stored
    # system_prompt drives the conversation. SET NULL so deleting a mission never
    # cascades into losing the session/transcript history.
    mission_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("missions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    room_name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    # Which LLM engine served this session; set from settings at session start.
    voice_engine: Mapped[str] = mapped_column(String(16), default=ENGINE_FAKE, nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
