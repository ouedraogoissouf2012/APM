from fastapi import FastAPI

app = FastAPI(title="APM Backend")


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
