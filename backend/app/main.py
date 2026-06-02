from fastapi import FastAPI

from app.api.routes import auth

app = FastAPI(title="APM Backend")

app.include_router(auth.router)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
