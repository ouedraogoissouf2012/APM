from fastapi import Depends

from app.config import get_settings
from app.core.engines import ENGINE_DEEPSEEK
from app.core.rate_limit import RateLimiter
from app.core.rate_limit_factory import build_rate_limiter
from app.features.conversation.dependencies import get_stt_provider
from app.features.conversation.factory import shared_llm_provider
from app.features.conversation.providers.interfaces import (
    SttProvider,
)
from app.features.conversation.providers.interfaces import (
    TextCompletionProvider as LlmProvider,
)
from app.features.minimal_pairs.coach import PairCoach
from app.features.minimal_pairs.service import MinimalPairsService
from app.features.shadowing.fake_llm import FakeShadowingLlm

_settings = get_settings()

# Process-wide limiter (reuses the shadowing budget — same drill family).
# Backend chosen from config (Redis when REDIS_URL is set, else in-memory with
# max_keys cap to prevent DoS via high-cardinality keys #234).
_minimal_pairs_rate_limiter = build_rate_limiter(
    namespace="minimal_pairs",
    max_hits=_settings.shadowing_rate_limit_max,
    window_seconds=_settings.shadowing_rate_limit_window_seconds,
    redis_url=_settings.redis_url,
    max_keys=_settings.rate_limit_max_keys,
)


def get_minimal_pairs_rate_limiter() -> RateLimiter:
    return _minimal_pairs_rate_limiter


def _coaching_llm() -> LlmProvider:
    # The pairs themselves are static content; only the coaching uses the LLM,
    # so it reuses the shadowing engine setting.
    settings = get_settings()
    if settings.shadowing_engine == ENGINE_DEEPSEEK:
        return shared_llm_provider(
            engine=ENGINE_DEEPSEEK,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            timeout_seconds=settings.deepseek_timeout_seconds,
            max_retries=settings.deepseek_max_retries,
            max_tokens=settings.deepseek_shadowing_max_tokens,
        )
    return FakeShadowingLlm()


def get_minimal_pairs_service(
    stt: SttProvider = Depends(get_stt_provider),
) -> MinimalPairsService:
    """Scoring an attempt requires a server STT (404 when STT_ENGINE=device)."""
    return MinimalPairsService(coach=PairCoach(_coaching_llm()), stt=stt)
