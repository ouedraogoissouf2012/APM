from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.rate_limit import InMemoryRateLimiter, RateLimiter
from app.database import get_db
from app.domain.exceptions import NotFoundError
from app.features.conversation.correction import TurnCorrector
from app.features.conversation.factory import shared_llm_provider
from app.features.conversation.providers.interfaces import SttProvider, TtsProvider
from app.features.conversation.providers.stt import build_stt_provider
from app.features.conversation.providers.tts import EdgeTtsProvider
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


def get_stt_provider() -> SttProvider:
    """Server-side transcription provider. 404 when STT_ENGINE=device: the
    client transcribes on-device and must not reach this endpoint."""
    settings = get_settings()
    provider = build_stt_provider(
        engine=settings.stt_engine,
        api_key=settings.groq_api_key,
        base_url=settings.groq_base_url,
        model=settings.groq_stt_model,
    )
    if provider is None:
        raise NotFoundError("Server-side transcription is not enabled")
    return provider


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
    # Server-side neural voice when TTS_ENGINE=edge; None keeps the on-device
    # system voice (default), so nothing changes until it is switched on.
    tts: TtsProvider | None = EdgeTtsProvider() if settings.tts_engine == "edge" else None
    return ConversationTurnService(
        sessions=SqlAlchemySessionRepository(db),
        transcripts=SqlAlchemyTranscriptRepository(db),
        profiles=SqlAlchemyProfileRepository(db),
        llm=llm,
        # Same shared provider: the correction is a second, bounded call run in
        # parallel with the reply. Fake engine -> no correction (honest).
        corrector=TurnCorrector(llm),
        tts=tts,
    )
