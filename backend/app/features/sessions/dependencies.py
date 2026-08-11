from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.features.auth.dependencies import get_user_repository
from app.features.auth.repository import UserRepository
from app.features.conversation.repository import (
    SqlAlchemyTranscriptRepository,
    TranscriptRepository,
)
from app.features.missions.repository import MissionRepository, SqlAlchemyMissionRepository
from app.features.sessions.repository import SessionRepository, SqlAlchemySessionRepository
from app.features.sessions.service import SessionService


def get_session_repository(db: AsyncSession = Depends(get_db)) -> SessionRepository:
    return SqlAlchemySessionRepository(db)


def get_transcript_repository(db: AsyncSession = Depends(get_db)) -> TranscriptRepository:
    return SqlAlchemyTranscriptRepository(db)


def get_mission_repository(db: AsyncSession = Depends(get_db)) -> MissionRepository:
    return SqlAlchemyMissionRepository(db)


def build_session_service(
    sessions: SessionRepository,
    users: UserRepository,
    transcripts: TranscriptRepository | None = None,
    missions: MissionRepository | None = None,
) -> SessionService:
    """Construct a SessionService from repositories. Shared by the sessions router
    and the conversation turn service (which reuses record_turn_activity for
    per-turn metering, #119)."""
    settings = get_settings()
    return SessionService(
        sessions,
        users,
        settings.free_tier_daily_minutes,
        transcripts=transcripts,
        voice_engine=settings.voice_engine,
        history_page_size=settings.session_history_page_size,
        missions=missions,
        inactivity_timeout_minutes=settings.session_inactivity_timeout_minutes,
        turn_meter_cap_minutes=settings.session_turn_meter_cap_minutes,
    )


def get_session_service(
    sessions: SessionRepository = Depends(get_session_repository),
    users: UserRepository = Depends(get_user_repository),
    transcripts: TranscriptRepository = Depends(get_transcript_repository),
    missions: MissionRepository = Depends(get_mission_repository),
) -> SessionService:
    return build_session_service(sessions, users, transcripts, missions)
