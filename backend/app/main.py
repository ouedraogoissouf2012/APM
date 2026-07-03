from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.middleware import RequestContextMiddleware
from app.config import get_settings
from app.core.logging import configure_logging
from app.features.auth.router import router as auth_router
from app.features.conversation.router import router as conversation_router
from app.features.debrief.router import router as debrief_router
from app.features.profile.router import router as profile_router
from app.features.sessions.router import router as sessions_router

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title="APM Backend")

app.add_middleware(RequestContextMiddleware)
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
app.include_router(conversation_router)
app.include_router(debrief_router)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
