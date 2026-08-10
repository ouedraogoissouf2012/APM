"""Observability (#235): unhandled exceptions are logged + normalized, the request
id reaches app logs, and /health actually pings the database.
"""

import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.errors import register_exception_handlers
from app.api.middleware import RequestContextMiddleware
from app.core.logging import RequestIdFilter, request_id_var
from app.database import get_db
from app.main import app as real_app


@pytest.mark.asyncio
async def test_unhandled_exception_returns_a_normalized_500():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise ValueError("kaboom")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/boom")

    assert resp.status_code == 500
    assert resp.json() == {
        "error": {"code": "InternalServerError", "message": "Internal server error"}
    }


@pytest.mark.asyncio
async def test_unhandled_exception_correlates_request_id_in_log_and_response():
    # Regression for #257: the 500's error log AND its response must carry the
    # request's id. The request-id contextvar is reset as the exception unwinds
    # (before the outermost 500 handler runs), so the handler must read the id from
    # the ASGI scope — otherwise the crash log is stamped with the "-" default and
    # can't be traced to the request that caused it.
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(RequestContextMiddleware)

    @app.get("/boom")
    async def boom() -> None:
        raise ValueError("kaboom")

    captured: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    handler = _Capture()
    handler.addFilter(RequestIdFilter())  # the same filter the app attaches
    err_logger = logging.getLogger("apm.error")
    err_logger.addHandler(handler)
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/boom", headers={"X-Request-ID": "REQ-12345"})
    finally:
        err_logger.removeHandler(handler)

    assert resp.status_code == 500
    # Echoed on the response so a user can quote it in a report.
    assert resp.headers.get("X-Request-ID") == "REQ-12345"
    # The crash log is correlated to the request, not the "-" default.
    errors = [r for r in captured if r.name == "apm.error"]
    assert len(errors) == 1
    assert errors[0].request_id == "REQ-12345"


class _OkDb:
    async def execute(self, *args, **kwargs) -> None:
        return None


class _DownDb:
    async def execute(self, *args, **kwargs) -> None:
        raise RuntimeError("database unreachable")


async def _hit_health() -> tuple[int, dict]:
    transport = ASGITransport(app=real_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")
    return resp.status_code, resp.json()


@pytest.mark.asyncio
async def test_health_is_ok_when_the_db_responds():
    async def _ok():
        yield _OkDb()

    real_app.dependency_overrides[get_db] = _ok
    try:
        status_code, body = await _hit_health()
    finally:
        real_app.dependency_overrides.clear()
    assert status_code == 200
    assert body == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_is_503_when_the_db_is_unreachable():
    async def _down():
        yield _DownDb()

    real_app.dependency_overrides[get_db] = _down
    try:
        status_code, body = await _hit_health()
    finally:
        real_app.dependency_overrides.clear()
    assert status_code == 503
    assert body == {"status": "unavailable"}


def test_request_id_filter_stamps_the_current_request_id():
    flt = RequestIdFilter()
    token = request_id_var.set("abc123")
    try:
        record = logging.makeLogRecord({"msg": "deep in a turn"})
        flt.filter(record)
        assert record.request_id == "abc123"
    finally:
        request_id_var.reset(token)


def test_request_id_filter_keeps_an_explicit_id():
    # The access log passes request_id via extra=; the filter must not clobber it.
    flt = RequestIdFilter()
    record = logging.makeLogRecord({"msg": "access", "request_id": "explicit"})
    flt.filter(record)
    assert record.request_id == "explicit"
