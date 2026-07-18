from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.livekit import LiveKitRoomTokenIssuer
from app.database import get_db
from app.features.auth.dependencies import get_user_repository
from app.features.auth.repository import UserRepository
from app.features.conversation.repository import (
    SqlAlchemyTranscriptRepository,
    TranscriptRepository,
)
from app.features.sessions.repository import SessionRepository, SqlAlchemySessionRepository
from app.features.sessions.service import SessionService


def get_session_repository(db: AsyncSession = Depends(get_db)) -> SessionRepository:
    return SqlAlchemySessionRepository(db)


def get_transcript_repository(db: AsyncSession = Depends(get_db)) -> TranscriptRepository:
    return SqlAlchemyTranscriptRepository(db)


def get_session_service(
    sessions: SessionRepository = Depends(get_session_repository),
    users: UserRepository = Depends(get_user_repository),
    transcripts: TranscriptRepository = Depends(get_transcript_repository),
) -> SessionService:
    settings = get_settings()
    return SessionService(
        sessions,
        users,
        settings.free_tier_daily_minutes,
        transcripts=transcripts,
        token_issuer=LiveKitRoomTokenIssuer(),
        voice_engine=settings.voice_engine,
        history_page_size=settings.session_history_page_size,
    )
