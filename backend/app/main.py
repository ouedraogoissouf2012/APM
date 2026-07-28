from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.middleware import RequestContextMiddleware
from app.config import get_settings
from app.core.engines import ENGINE_FAKE
from app.core.logging import configure_logging
from app.features.auth.router import router as auth_router
from app.features.conversation.router import router as conversation_router
from app.features.conversation.stt_router import router as stt_router
from app.features.debrief.router import router as debrief_router
from app.features.missions.router import router as missions_router
from app.features.profile.router import router as profile_router
from app.features.sessions.router import router as sessions_router

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title="APM Backend")

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
app.include_router(profile_router)
app.include_router(sessions_router)
app.include_router(missions_router)
app.include_router(conversation_router)
app.include_router(stt_router)
app.include_router(debrief_router)


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
        # When true, the backend streams synthesized neural audio; the client
        # plays it instead of speaking with the on-device system voice.
        "server_tts": s.tts_engine != "device",
        # When true, the client records audio and POSTs it to /transcribe
        # instead of using the (weaker) on-device browser recognizer.
        "server_stt": s.stt_engine != "device",
    }
