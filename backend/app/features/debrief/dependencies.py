from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.engines import ENGINE_DEEPSEEK
from app.core.rate_limit import InMemoryRateLimiter, RateLimiter
from app.database import get_db
from app.features.auth.repository import SqlAlchemyUserRepository
from app.features.conversation.factory import shared_llm_provider
from app.features.conversation.providers.interfaces import (
    TextCompletionProvider as LlmProvider,
)
from app.features.conversation.repository import SqlAlchemyTranscriptRepository
from app.features.debrief.analyzer import DebriefAnalyzer
from app.features.debrief.fake_llm import FakeDebriefLlm
from app.features.debrief.repository import SqlAlchemyDebriefRepository
from app.features.debrief.service import DebriefService
from app.features.profile.repository import SqlAlchemyProfileRepository
from app.features.sessions.repository import SqlAlchemySessionRepository

_settings = get_settings()

# Process-wide limiter. Swap for RedisRateLimiter to scale across instances;
# the RateLimiter interface and route callers stay unchanged.
_debrief_rate_limiter = InMemoryRateLimiter(
    max_hits=_settings.debrief_rate_limit_max,
    window_seconds=_settings.debrief_rate_limit_window_seconds,
)


def get_debrief_rate_limiter() -> RateLimiter:
    return _debrief_rate_limiter


def get_debrief_service(db: AsyncSession = Depends(get_db)) -> DebriefService:
    settings = get_settings()
    # Default "fake" returns a valid (generic) debrief; "deepseek" does real analysis.
    llm: LlmProvider
    if settings.debrief_engine == ENGINE_DEEPSEEK:
        # Cached: one LLM client (one connection pool) per configuration.
        llm = shared_llm_provider(
            engine=ENGINE_DEEPSEEK,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            timeout_seconds=settings.deepseek_timeout_seconds,
            max_retries=settings.deepseek_max_retries,
            max_tokens=settings.deepseek_debrief_max_tokens,
        )
    else:
        llm = FakeDebriefLlm()
    return DebriefService(
        sessions=SqlAlchemySessionRepository(db),
        transcripts=SqlAlchemyTranscriptRepository(db),
        debriefs=SqlAlchemyDebriefRepository(db),
        analyzer=DebriefAnalyzer(llm, max_errors=settings.debrief_max_errors),
        profiles=SqlAlchemyProfileRepository(db),
        users=SqlAlchemyUserRepository(db),
    )
