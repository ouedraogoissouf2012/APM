import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import register_exception_handlers
from app.api.middleware import BodySizeLimitMiddleware, RequestContextMiddleware
from app.config import get_settings
from app.core.engines import ENGINE_FAKE
from app.core.logging import configure_logging
from app.database import get_db
from app.features.analytics.router import router as analytics_router
from app.features.auth.router import router as auth_router
from app.features.billing.router import router as billing_router
from app.features.conversation.router import router as conversation_router
from app.features.conversation.stt_router import router as stt_router
from app.features.debrief.router import router as debrief_router
from app.features.minimal_pairs.router import router as minimal_pairs_router
from app.features.missions.router import router as missions_router
from app.features.onboarding.router import router as onboarding_router
from app.features.profile.router import router as profile_router
from app.features.progress.router import router as progress_router
from app.features.proof.router import router as proof_router
from app.features.review.router import router as review_router
from app.features.sessions.router import router as sessions_router
from app.features.shadowing.router import router as shadowing_router
from app.features.streaks.router import router as streaks_router
from app.features.transfer.router import router as transfer_router
from app.features.vocabulary.router import router as vocabulary_router
from app.features.voice_consent.router import router as voice_consent_router
from app.features.voice_data.router import router as voice_data_router

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

    # Purge tables with unbounded growth (#239/#271) on an interval, in-process.
    purge_task = asyncio.create_task(_purge_loop()) if settings.purge_interval_seconds > 0 else None
    try:
        yield
    finally:
        if purge_task is not None:
            purge_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await purge_task


async def _purge_loop() -> None:
    """Run the unbounded-table purge on an interval for the process lifetime (#271):
    expired refresh tokens, old idempotency keys, old analytics events. Each iteration
    opens its own DB session and is fully best-effort — a failed sweep is logged and
    the loop keeps going."""
    from app.database import SessionLocal
    from app.features.purge.task import purge_expired_entries

    log = logging.getLogger("apm")
    while True:
        await asyncio.sleep(settings.purge_interval_seconds)
        try:
            async with SessionLocal() as session:
                await purge_expired_entries(session)
        except Exception:
            log.warning("Periodic purge iteration failed", exc_info=True)


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


def _docs_enabled(app_env: str) -> bool:
    """Disable the interactive docs (Swagger/ReDoc) and the raw OpenAPI schema in
    production (#231): they enumerate every route, including admin-only ones,
    which is reconnaissance a production deployment should not hand out for free.
    Kept on everywhere else (dev/test/staging) so they stay useful to build against."""
    return app_env != "production"


_docs_url = "/docs" if _docs_enabled(settings.app_env) else None
_redoc_url = "/redoc" if _docs_enabled(settings.app_env) else None
_openapi_url = "/openapi.json" if _docs_enabled(settings.app_env) else None

app = FastAPI(
    title="APM Backend",
    lifespan=lifespan,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
)

# Innermost: reject an oversized body with 413 before Starlette buffers it (#221),
# while its response still flows out through the request-context logging + headers.
app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_body_bytes)
app.add_middleware(RequestContextMiddleware, enable_hsts=settings.app_env == "production")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

# Feature routers, registered from one list so adding a feature is a single edit
# and the mounted set is obvious at a glance. Order is not significant — FastAPI
# matches by path, and no two routers share a prefix.
_ROUTERS = (
    auth_router,
    billing_router,
    analytics_router,
    profile_router,
    progress_router,
    proof_router,
    review_router,
    streaks_router,
    transfer_router,
    onboarding_router,
    sessions_router,
    missions_router,
    conversation_router,
    stt_router,
    shadowing_router,
    minimal_pairs_router,
    debrief_router,
    vocabulary_router,
    voice_consent_router,
    voice_data_router,
)
for _router in _ROUTERS:
    app.include_router(_router)


@app.get("/health", tags=["meta"])
async def health(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Readiness check that actually pings the DB (#235): an instance whose database
    is unreachable must report 503, or a load balancer keeps routing traffic to a
    worker where every DB endpoint 500s."""
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        logging.getLogger("apm").warning("Health check failed: DB unreachable", exc_info=True)
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return JSONResponse(content={"status": "ok"})


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
