from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.rate_limit import InMemoryRateLimiter, RateLimiter
from app.database import get_db
from app.features.conversation.correction import TurnCorrector
from app.features.conversation.factory import shared_llm_provider
from app.features.conversation.repository import SqlAlchemyTranscriptRepository
from app.features.conversation.turn_service import ConversationTurnService
from app.features.profile.repository import SqlAlchemyProfileRepository
from app.features.sessions.repository import SqlAlchemySessionRepository

_settings = get_settings()

# Process-wide limiter. Swap for RedisRateLimiter to scale across instances;
# the RateLimiter interface and route callers stay unchanged.
_conversation_rate_limiter = InMemoryRateLimiter(
    max_hits=_settings.conversation_rate_limit_max,
    window_seconds=_settings.conversation_rate_limit_window_seconds,
)


def get_conversation_rate_limiter() -> RateLimiter:
    return _conversation_rate_limiter


def get_conversation_turn_service(
    db: AsyncSession = Depends(get_db),
) -> ConversationTurnService:
    settings = get_settings()
    # Cached: one LLM client (one connection pool) per configuration, not per request.
    llm = shared_llm_provider(
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
        # Same shared provider: the correction is a second, bounded call run in
        # parallel with the reply. Fake engine -> no correction (honest).
        corrector=TurnCorrector(llm),
    )
