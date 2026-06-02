from fastapi import FastAPI

from app.api.routes import auth, profile

app = FastAPI(title="APM Backend")

app.include_router(auth.router)
app.include_router(profile.router)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
