from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.engines import ENGINE_DEEPSEEK
from app.core.rate_limit import InMemoryRateLimiter, RateLimiter
from app.database import get_db
from app.features.conversation.factory import shared_llm_provider
from app.features.conversation.providers.interfaces import (
    TextCompletionProvider as LlmProvider,
)
from app.features.missions.compiler import MissionCompiler
from app.features.missions.fake_llm import FakeMissionLlm
from app.features.missions.repository import SqlAlchemyMissionRepository
from app.features.missions.service import MissionService

_settings = get_settings()

# Process-wide limiter. Swap for RedisRateLimiter to scale across instances;
# the RateLimiter interface and route callers stay unchanged.
_mission_rate_limiter = InMemoryRateLimiter(
    max_hits=_settings.mission_rate_limit_max,
    window_seconds=_settings.mission_rate_limit_window_seconds,
)


def get_mission_rate_limiter() -> RateLimiter:
    return _mission_rate_limiter


def get_mission_service(db: AsyncSession = Depends(get_db)) -> MissionService:
    settings = get_settings()
    # Default "fake" returns a valid (generic) brief; "deepseek" does real compilation.
    llm: LlmProvider
    if settings.mission_engine == ENGINE_DEEPSEEK:
        # Cached: one LLM client (one connection pool) per configuration.
        llm = shared_llm_provider(
            engine=ENGINE_DEEPSEEK,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            timeout_seconds=settings.deepseek_timeout_seconds,
            max_retries=settings.deepseek_max_retries,
            max_tokens=settings.deepseek_mission_max_tokens,
        )
    else:
        llm = FakeMissionLlm()
    return MissionService(
        missions=SqlAlchemyMissionRepository(db),
        compiler=MissionCompiler(llm),
    )
