from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.engines import ENGINE_FAKE
from app.core.llm.factory import build_feature_llm
from app.core.llm.interfaces import (
    TextCompletionProvider as LlmProvider,
)
from app.core.rate_limit import RateLimiter
from app.core.rate_limit_factory import build_rate_limiter
from app.database import get_db
from app.features.missions.compiler import MissionCompiler
from app.features.missions.fake_llm import FakeMissionLlm
from app.features.missions.repository import SqlAlchemyMissionRepository
from app.features.missions.service import MissionService

_settings = get_settings()

# Process-wide limiter, backend chosen from config (Redis when REDIS_URL is set,
# else in-memory with max_keys cap to prevent DoS via high-cardinality keys #234).
# The RateLimiter interface and route callers stay unchanged.
_mission_rate_limiter = build_rate_limiter(
    namespace="mission",
    max_hits=_settings.mission_rate_limit_max,
    window_seconds=_settings.mission_rate_limit_window_seconds,
    redis_url=_settings.redis_url,
    max_keys=_settings.rate_limit_max_keys,
)


def get_mission_rate_limiter() -> RateLimiter:
    return _mission_rate_limiter


def get_mission_service(db: AsyncSession = Depends(get_db)) -> MissionService:
    settings = get_settings()
    # Default "fake" returns a valid (generic) brief. A real engine does real
    # compilation — and via build_feature_llm (like the conversation/debrief), so
    # missions get the SAME options, including the robust "groq_fallback" chain
    # (Groq -> DeepSeek). Missions no longer break if the DeepSeek key alone dies (#209).
    llm: LlmProvider
    if settings.mission_engine == ENGINE_FAKE:
        llm = FakeMissionLlm()
    else:
        llm = build_feature_llm(
            settings.mission_engine, settings, settings.deepseek_mission_max_tokens
        )
    return MissionService(
        missions=SqlAlchemyMissionRepository(db),
        compiler=MissionCompiler(llm),
    )
