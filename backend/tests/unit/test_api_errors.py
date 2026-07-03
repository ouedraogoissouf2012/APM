from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.errors import register_exception_handlers
from app.domain.exceptions import LlmProviderError


def test_llm_provider_error_returns_normalized_502():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom():
        raise LlmProviderError("LLM provider failed")

    response = TestClient(app).get("/boom")

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "LlmProviderError",
            "message": "LLM provider failed",
        }
    }
