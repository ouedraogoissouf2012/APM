from functools import lru_cache

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.rate_limit import RateLimiter
from app.core.rate_limit_factory import build_rate_limiter
from app.database import get_db
from app.domain.exceptions import NotFoundError
from app.features.auth.repository import SqlAlchemyUserRepository
from app.features.conversation.correction import TurnCorrector
from app.features.conversation.factory import build_feature_llm
from app.features.conversation.providers.caching_tts import CachingTtsProvider
from app.features.conversation.providers.interfaces import SttProvider, TtsProvider
from app.features.conversation.providers.stt import shared_stt_provider
from app.features.conversation.providers.tts import EdgeTtsProvider
from app.features.conversation.providers.tts_cache_factory import build_tts_cache
from app.features.conversation.repository import SqlAlchemyTranscriptRepository
from app.features.conversation.turn_service import ConversationTurnService
from app.features.missions.repository import SqlAlchemyMissionRepository
from app.features.profile.repository import SqlAlchemyProfileRepository
from app.features.sessions.dependencies import build_session_service
from app.features.sessions.repository import SqlAlchemySessionRepository

_settings = get_settings()

# Process-wide limiter, backend chosen from config (Redis when REDIS_URL is set,
# else in-memory with max_keys cap to prevent DoS via high-cardinality keys #234).
# The RateLimiter interface and route callers stay unchanged.
_conversation_rate_limiter = build_rate_limiter(
    namespace="conversation",
    max_hits=_settings.conversation_rate_limit_max,
    window_seconds=_settings.conversation_rate_limit_window_seconds,
    redis_url=_settings.redis_url,
    max_keys=_settings.rate_limit_max_keys,
)


def get_conversation_rate_limiter() -> RateLimiter:
    return _conversation_rate_limiter


def get_stt_provider() -> SttProvider:
    """Server-side transcription provider. 404 when STT_ENGINE=device: the
    client transcribes on-device and must not reach this endpoint."""
    settings = get_settings()
    provider = shared_stt_provider(
        engine=settings.stt_engine,
        api_key=settings.groq_api_key,
        base_url=settings.groq_base_url,
        model=settings.groq_stt_model,
        prompt=settings.groq_stt_prompt,
    )
    if provider is None:
        raise NotFoundError("Server-side transcription is not enabled")
    return provider


@lru_cache(maxsize=1)
def _shared_tts_provider() -> TtsProvider:
    """One process-wide TTS provider, wrapped in a content-addressed cache (#123, #234).

    Repeated lines (identical openings, replays) are not re-synthesized. Shared across
    requests/users — that's what makes the cache pay off. Caching disabled when
    tts_cache_max_entries == 0.

    In production (multi-worker), REDIS_URL enables a shared Redis cache; dev/tests
    use in-memory LRU.
    """
    settings = get_settings()
    base = EdgeTtsProvider()
    if settings.tts_cache_max_entries <= 0:
        return base
    cache = build_tts_cache(
        max_entries=settings.tts_cache_max_entries,
        redis_url=settings.redis_url,
    )
    return CachingTtsProvider(base, cache)


def get_tts_provider() -> TtsProvider:
    """Server-side neural TTS. 404 when TTS_ENGINE=device: the client speaks with
    its on-device voice and must not reach a server TTS endpoint."""
    settings = get_settings()
    if settings.tts_engine != "edge":
        raise NotFoundError("Server-side text-to-speech is not enabled")
    return _shared_tts_provider()


def get_conversation_turn_service(
    db: AsyncSession = Depends(get_db),
) -> ConversationTurnService:
    settings = get_settings()
    # The conversation LLM for the configured engine. "groq_fallback" gives the
    # Groq -> DeepSeek chain (fast + free by day, unlimited paid as a safety net);
    # "groq"/"deepseek" a single cached provider. History is engine-neutral, so a
    # mid-conversation failover is seamless.
    llm = build_feature_llm(
        settings.voice_engine, settings, settings.deepseek_conversation_max_tokens
    )
    # Server-side neural voice when TTS_ENGINE=edge; None keeps the on-device
    # system voice (default). Same cached provider as the /tts endpoint (#123).
    tts: TtsProvider | None = _shared_tts_provider() if settings.tts_engine == "edge" else None
    sessions = SqlAlchemySessionRepository(db)
    # A SessionService sharing this request's db session, used ONLY to meter the
    # quota per turn (#119) via record_turn_activity — so an abandoned session
    # can't run unlimited free turns.
    session_service = build_session_service(sessions, SqlAlchemyUserRepository(db))
    # The correction is a second, bounded LLM call in parallel with the reply
    # (#123 cost control): disabled entirely by config, else skips short utterances.
    corrector = (
        TurnCorrector(llm, min_words=settings.correction_min_words)
        if settings.correction_enabled
        else None
    )
    return ConversationTurnService(
        sessions=sessions,
        transcripts=SqlAlchemyTranscriptRepository(db),
        profiles=SqlAlchemyProfileRepository(db),
        llm=llm,
        corrector=corrector,
        tts=tts,
        # Drives a mission session with the mission's stored persona prompt.
        missions=SqlAlchemyMissionRepository(db),
        meter=session_service.record_turn_activity,
        history_max_messages=settings.conversation_history_max_messages,
    )
