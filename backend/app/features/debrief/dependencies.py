from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.engines import ENGINE_FAKE
from app.core.rate_limit import RateLimiter
from app.core.rate_limit_factory import build_rate_limiter
from app.database import get_db
from app.features.auth.repository import SqlAlchemyUserRepository
from app.features.conversation.factory import build_feature_llm
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
_debrief_rate_limiter = build_rate_limiter(
    namespace="debrief",
    max_hits=_settings.debrief_rate_limit_max,
    window_seconds=_settings.debrief_rate_limit_window_seconds,
    redis_url=_settings.redis_url,
)


def get_debrief_rate_limiter() -> RateLimiter:
    return _debrief_rate_limiter


def get_debrief_service(db: AsyncSession = Depends(get_db)) -> DebriefService:
    settings = get_settings()
    # Default "fake" returns a valid (generic) debrief; "deepseek"/"groq" do real
    # analysis (groq is much faster — the debrief no longer stalls at end of session).
    llm: LlmProvider
    if settings.debrief_engine == ENGINE_FAKE:
        llm = FakeDebriefLlm()
    else:
        # Same engine options as the conversation, including "groq_fallback".
        llm = build_feature_llm(
            settings.debrief_engine, settings, settings.deepseek_debrief_max_tokens
        )
    return DebriefService(
        sessions=SqlAlchemySessionRepository(db),
        transcripts=SqlAlchemyTranscriptRepository(db),
        debriefs=SqlAlchemyDebriefRepository(db),
        analyzer=DebriefAnalyzer(llm, max_errors=settings.debrief_max_errors),
        profiles=SqlAlchemyProfileRepository(db),
        users=SqlAlchemyUserRepository(db),
    )
