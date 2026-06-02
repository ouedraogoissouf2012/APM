from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.routes import auth, profile, sessions

app = FastAPI(title="APM Backend")

register_exception_handlers(app)

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(sessions.router)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
