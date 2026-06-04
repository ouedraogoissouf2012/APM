from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.features.conversation.factory import build_llm_provider
from app.features.conversation.repository import SqlAlchemyTranscriptRepository
from app.features.debrief.analyzer import DebriefAnalyzer
from app.features.debrief.repository import SqlAlchemyDebriefRepository
from app.features.debrief.service import DebriefService
from app.features.sessions.repository import SqlAlchemySessionRepository


def get_debrief_service(db: AsyncSession = Depends(get_db)) -> DebriefService:
    settings = get_settings()
    llm = build_llm_provider(
        engine=settings.debrief_engine,
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
    )
    return DebriefService(
        sessions=SqlAlchemySessionRepository(db),
        transcripts=SqlAlchemyTranscriptRepository(db),
        debriefs=SqlAlchemyDebriefRepository(db),
        analyzer=DebriefAnalyzer(llm),
    )
