from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.features.conversation.factory import build_llm_provider
from app.features.conversation.repository import SqlAlchemyTranscriptRepository
from app.features.conversation.turn_service import ConversationTurnService
from app.features.profile.repository import SqlAlchemyProfileRepository
from app.features.sessions.repository import SqlAlchemySessionRepository


def get_conversation_turn_service(
    db: AsyncSession = Depends(get_db),
) -> ConversationTurnService:
    settings = get_settings()
    llm = build_llm_provider(
        engine=settings.voice_engine,
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        timeout_seconds=settings.deepseek_timeout_seconds,
        max_retries=settings.deepseek_max_retries,
        max_tokens=settings.deepseek_conversation_max_tokens,
    )
    return ConversationTurnService(
        sessions=SqlAlchemySessionRepository(db),
        transcripts=SqlAlchemyTranscriptRepository(db),
        profiles=SqlAlchemyProfileRepository(db),
        llm=llm,
    )
