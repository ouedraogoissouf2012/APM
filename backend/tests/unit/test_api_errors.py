from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

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


def test_raw_http_exception_is_normalized_not_bare_detail():
    """A router that raises fastapi.HTTPException directly (a 403 consent gate, a
    422 pre-check, ...) must get the SAME envelope as a DomainError, not Starlette's
    default {"detail": ...} body (#241)."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/consent")
    async def consent():
        raise HTTPException(status_code=403, detail="Transcription consent has been revoked")

    response = TestClient(app).get("/consent")

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "Forbidden",
            "message": "Transcription consent has been revoked",
        }
    }


def test_request_validation_error_returns_normalized_422():
    """A field that fails Pydantic validation (e.g. native_language over its max
    length) must return 422 with the normalized envelope, not FastAPI's default
    {"detail": [...]} list (#241)."""
    app = FastAPI()
    register_exception_handlers(app)

    class Payload(BaseModel):
        name: str = Field(max_length=3)

    @app.post("/echo")
    async def echo(payload: Payload) -> Payload:
        return payload

    response = TestClient(app).post("/echo", json={"name": "too-long"})

    assert response.status_code == 422
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message"}
    assert body["error"]["code"] == "ValidationError"
    assert "name" in body["error"]["message"]


def test_unmatched_route_returns_normalized_404_not_bare_detail():
    """Starlette's router raises starlette.exceptions.HTTPException directly for an
    unmatched path — a DIFFERENT class from fastapi.HTTPException (its subclass), so
    the handler must be registered against the Starlette base class or this 404 keeps
    FastAPI's default {"detail": "Not Found"} body (#241)."""
    app = FastAPI()
    register_exception_handlers(app)

    response = TestClient(app).get("/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "NotFound", "message": "Not Found"}}


def test_integrity_error_returns_normalized_409():
    """A commit that races past an application-level ON CONFLICT guard (or hits a
    table with no such guard) can still raise a raw IntegrityError. This must
    return 409 with the normalized envelope, not fall through to the generic
    unhandled-exception 500 (#362)."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom():
        raise IntegrityError("INSERT INTO t (id) VALUES (1)", {}, Exception("duplicate key"))

    response = TestClient(app).get("/boom")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "IntegrityError",
            "message": "Conflicting data",
        }
    }


def test_wrong_method_returns_normalized_405_not_bare_detail():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/only-get")
    async def only_get():
        return {}

    response = TestClient(app).post("/only-get")

    assert response.status_code == 405
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message"}
    assert body["error"]["code"] == "MethodNotAllowed"
