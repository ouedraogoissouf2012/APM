from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.engines import ENGINE_FAKE
from app.database import Base


class ConversationSession(Base):
    __tablename__ = "sessions"
    # Serves get_active_for_user's plain user_id filter as a leftmost-prefix
    # match while also covering list_recent_for_user's ORDER BY started_at DESC
    # (satisfiable via a backward index scan) — replaces the old single-column
    # ix_sessions_user_id, on the model of #288 (#359).
    __table_args__ = (
        Index("ix_sessions_user_id_started_at", "user_id", "started_at"),
        # #428: "one active session per user" is otherwise only enforced in
        # start() + User.lock. A partial unique index is the real invariant.
        Index(
            "uq_sessions_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False)  # "scenario" | "free" | "mission"
    scenario_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Set when the session runs a compiled mission (mode="mission"); its stored
    # system_prompt drives the conversation. SET NULL so deleting a mission never
    # cascades into losing the session/transcript history.
    mission_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("missions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Which LLM engine served this session; set from settings at session start.
    voice_engine: Mapped[str] = mapped_column(String(16), default=ENGINE_FAKE, nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Bumped on every turn (#119) so per-turn metering charges the real gap and a
    # lazy reaper can auto-close a session abandoned without /end. Defaults to the
    # start time for rows created before this column existed.
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
