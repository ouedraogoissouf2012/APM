import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.middleware import RequestContextMiddleware
from app.config import get_settings
from app.core.engines import ENGINE_FAKE
from app.core.logging import configure_logging
from app.features.auth.router import router as auth_router
from app.features.billing.router import router as billing_router
from app.features.conversation.router import router as conversation_router
from app.features.conversation.stt_router import router as stt_router
from app.features.debrief.router import router as debrief_router
from app.features.minimal_pairs.router import router as minimal_pairs_router
from app.features.missions.router import router as missions_router
from app.features.onboarding.router import router as onboarding_router
from app.features.profile.router import router as profile_router
from app.features.sessions.router import router as sessions_router
from app.features.shadowing.router import router as shadowing_router
from app.features.vocabulary.router import router as vocabulary_router

settings = get_settings()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Warm up the external voice services once at startup so the FIRST learner
    # doesn't pay their connection cold-start (DNS + TLS, ~1-3 s) on their first
    # turn. Best-effort: any failure is logged and ignored — the services still
    # work per request.
    _log = logging.getLogger("apm")
    if settings.tts_engine == "edge":
        try:
            from app.features.conversation.dependencies import get_tts_provider

            await get_tts_provider().synthesize("Hello.")
            _log.info("TTS warm-up done")
        except Exception:
            _log.warning("TTS warm-up failed", exc_info=True)
    if settings.stt_engine == "groq":
        try:
            from app.features.conversation.dependencies import get_stt_provider

            # A ~50 ms silent WAV: opens the Groq connection (DNS+TLS+pool) so the
            # first real transcription reuses a warm keep-alive connection.
            await get_stt_provider().transcribe(_silent_wav())
            _log.info("STT warm-up done")
        except Exception:
            _log.warning("STT warm-up failed", exc_info=True)
    if settings.voice_engine in ("deepseek", "groq", "groq_fallback"):
        try:
            from app.features.conversation.factory import build_feature_llm

            # A tiny completion opens the LLM connection(s) so the first learner turn
            # reuses a warm connection (no per-request DNS+TLS on the first reply).
            # For the fallback engine this warms Groq (DeepSeek warms on first use).
            llm = build_feature_llm(settings.voice_engine, settings, max_tokens=1)
            await llm.complete("Say hi.", [])
            _log.info("LLM warm-up done")
        except Exception:
            _log.warning("LLM warm-up failed", exc_info=True)
    yield


def _silent_wav() -> bytes:
    """A minimal valid WAV (a few ms of silence) to warm the STT connection."""
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16_000)
        w.writeframes(b"\x00\x00" * 800)  # 800 samples ~ 50 ms of silence
    return buf.getvalue()


app = FastAPI(title="APM Backend", lifespan=lifespan)

app.add_middleware(RequestContextMiddleware, enable_hsts=settings.app_env == "production")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(profile_router)
app.include_router(onboarding_router)
app.include_router(sessions_router)
app.include_router(missions_router)
app.include_router(conversation_router)
app.include_router(stt_router)
app.include_router(shadowing_router)
app.include_router(minimal_pairs_router)
app.include_router(debrief_router)
app.include_router(vocabulary_router)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/config", tags=["meta"])
async def public_config() -> dict[str, bool]:
    """Non-sensitive runtime flags the client needs. `demo_mode` is true when no
    real LLM is configured (engine=fake): the app then invents replies and skips
    corrections, so the UI must say so rather than pretend it is teaching."""
    s = get_settings()
    return {
        "demo_mode": s.voice_engine == ENGINE_FAKE,
        "debrief_demo_mode": s.debrief_engine == ENGINE_FAKE,
        # When true, missions are compiled by the fake engine (generic brief).
        "mission_demo_mode": s.mission_engine == ENGINE_FAKE,
        # When true, shadowing phrases/coaching come from the fake engine.
        "shadowing_demo_mode": s.shadowing_engine == ENGINE_FAKE,
        # When true, the backend streams synthesized neural audio; the client
        # plays it instead of speaking with the on-device system voice.
        "server_tts": s.tts_engine != "device",
        # When true, the client records audio and POSTs it to /transcribe
        # instead of using the (weaker) on-device browser recognizer.
        "server_stt": s.stt_engine != "device",
    }
