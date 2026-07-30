from fastapi import Depends

from app.config import get_settings
from app.core.engines import ENGINE_DEEPSEEK
from app.core.rate_limit import InMemoryRateLimiter, RateLimiter
from app.features.conversation.dependencies import get_stt_provider
from app.features.conversation.factory import shared_llm_provider
from app.features.conversation.providers.interfaces import (
    SttProvider,
)
from app.features.conversation.providers.interfaces import (
    TextCompletionProvider as LlmProvider,
)
from app.features.pronunciation.provider import (
    PronunciationProvider,
    shared_pronunciation_provider,
)
from app.features.shadowing.coach import ShadowingCoach
from app.features.shadowing.fake_llm import FakeShadowingLlm
from app.features.shadowing.generator import PhraseGenerator
from app.features.shadowing.service import ShadowingService

_settings = get_settings()

# Process-wide limiter. Swap for RedisRateLimiter to scale across instances.
_shadowing_rate_limiter = InMemoryRateLimiter(
    max_hits=_settings.shadowing_rate_limit_max,
    window_seconds=_settings.shadowing_rate_limit_window_seconds,
)


def get_shadowing_rate_limiter() -> RateLimiter:
    return _shadowing_rate_limiter


def _shadowing_llm() -> LlmProvider:
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


def get_shadowing_service() -> ShadowingService:
    """Service for generating phrases — does NOT require a server STT."""
    llm = _shadowing_llm()
    return ShadowingService(generator=PhraseGenerator(llm), coach=ShadowingCoach(llm))


def _pronunciation_provider() -> PronunciationProvider:
    settings = get_settings()
    return shared_pronunciation_provider(
        engine=settings.pronunciation_engine,
        service_url=settings.gop_service_url,
        timeout_seconds=settings.gop_timeout_seconds,
    )


def get_shadowing_service_with_stt(
    stt: SttProvider = Depends(get_stt_provider),
) -> ShadowingService:
    """Service for scoring an attempt — requires a server STT (404 when device).
    The pronunciation engine (GOP) is attached too; it is "fake" by default, so
    phoneme scores are empty unless PRONUNCIATION_ENGINE=gop is configured."""
    llm = _shadowing_llm()
    return ShadowingService(
        generator=PhraseGenerator(llm),
        coach=ShadowingCoach(llm),
        stt=stt,
        pronunciation=_pronunciation_provider(),
    )
