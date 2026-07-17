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
    return SessionService(
        sessions, users, get_settings().free_tier_daily_minutes, transcripts=transcripts
    )
