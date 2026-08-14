import logging

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from sqlalchemy.exc import DataError, IntegrityError

from app.api.errors import register_exception_handlers
from app.domain.exceptions import AuthenticationError, LlmProviderError


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


def test_domain_error_mapped_to_5xx_is_logged_with_stack(caplog):
    """A DomainError mapped to a 5xx (LlmProviderError -> 502) is an external
    dependency failure an operator must see (#402) — unlike the 4xx branch below,
    silence here means an STT/debrief outage is only root-causable by reproducing
    it live."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom():
        raise LlmProviderError("Transcription failed")

    with caplog.at_level(logging.WARNING, logger="apm.error"):
        response = TestClient(app).get("/boom")

    assert response.status_code == 502
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelno == logging.WARNING
    assert record.exc_info is not None  # the stack must be captured


def test_domain_error_mapped_to_4xx_is_not_logged(caplog):
    """4xx DomainErrors are expected client outcomes (bad credentials, not-found,
    ...) — logging every one would drown real signal in noise."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom():
        raise AuthenticationError("Invalid token")

    with caplog.at_level(logging.WARNING, logger="apm.error"):
        response = TestClient(app).get("/boom")

    assert response.status_code == 401
    assert caplog.records == []


def test_integrity_error_is_logged_despite_its_409_status(caplog):
    """An IntegrityError reaching this net is by definition a surprise (a commit
    that bypassed an application-level ON CONFLICT guard) disguised as a routine
    409 — it must be logged even though the response status is a 4xx (#402)."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom():
        raise IntegrityError("INSERT INTO t (id) VALUES (1)", {}, Exception("duplicate key"))

    with caplog.at_level(logging.WARNING, logger="apm.error"):
        response = TestClient(app).get("/boom")

    assert response.status_code == 409
    assert len(caplog.records) == 1
    record = caplog.records[0]
    # Logged value-free (#402 hardening): no exc_info, so the driver DETAIL / SQL /
    # bound parameters (which can carry the conflicting value or credentials) never
    # reach the log — only the error class + method + path do.
    assert record.exc_info is None
    assert "IntegrityError" in record.getMessage()
    assert "duplicate key" not in caplog.text


def test_data_error_is_logged_despite_its_422_status(caplog):
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom():
        raise DataError("INSERT INTO t (n) VALUES (999999999999)", {}, Exception("out of range"))

    with caplog.at_level(logging.WARNING, logger="apm.error"):
        response = TestClient(app).get("/boom")

    assert response.status_code == 422
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.exc_info is None
    assert "DataError" in record.getMessage()
    assert "out of range" not in caplog.text


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
