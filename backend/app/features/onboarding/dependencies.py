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
from app.features.auth.repository import SqlAlchemyUserRepository
from app.features.debrief.analyzer import DebriefAnalyzer
from app.features.debrief.fake_llm import FakeDebriefLlm
from app.features.onboarding.service import OnboardingService
from app.features.profile.repository import SqlAlchemyProfileRepository

_settings = get_settings()

# One placement per new account is the normal path; the limiter guards against a
# client hammering the (LLM-backed) endpoint. Reuses the shared limiter factory.
_onboarding_rate_limiter = build_rate_limiter(
    namespace="onboarding",
    max_hits=_settings.debrief_rate_limit_max,
    window_seconds=_settings.debrief_rate_limit_window_seconds,
    redis_url=_settings.redis_url,
)


def get_onboarding_rate_limiter() -> RateLimiter:
    return _onboarding_rate_limiter


def get_onboarding_service(db: AsyncSession = Depends(get_db)) -> OnboardingService:
    settings = get_settings()
    # Same engine selection as the debrief: the placement reuses the debrief
    # analyzer to estimate CEFR, so it uses the debrief engine.
    llm: LlmProvider
    if settings.debrief_engine == ENGINE_FAKE:
        llm = FakeDebriefLlm()
    else:
        llm = build_feature_llm(
            settings.debrief_engine, settings, settings.deepseek_debrief_max_tokens
        )
    return OnboardingService(
        analyzer=DebriefAnalyzer(
            llm,
            max_errors=settings.debrief_max_errors,
            max_learner_turns=settings.debrief_max_learner_turns,
        ),
        profiles=SqlAlchemyProfileRepository(db),
        users=SqlAlchemyUserRepository(db),
    )
