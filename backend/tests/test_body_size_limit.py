"""BodySizeLimitMiddleware (#221): reject an oversized request body with 413
BEFORE Starlette buffers it, so an unauthenticated multi-GB POST can't OOM the
worker. Pure middleware test on a minimal app — no DB, no settings.
"""

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.api.errors import register_exception_handlers
from app.api.middleware import BodySizeLimitMiddleware

_MAX = 100  # a tiny ceiling so tests don't shuffle megabytes around


def _app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=_MAX)

    @app.post("/echo")
    async def echo(request: Request) -> dict[str, int]:
        body = await request.body()
        return {"len": len(body)}

    return app


def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_body_under_limit_passes():
    async with _client(_app()) as ac:
        resp = await ac.post("/echo", content=b"x" * 50)
    assert resp.status_code == 200
    assert resp.json() == {"len": 50}


@pytest.mark.asyncio
async def test_declared_oversized_content_length_rejected_before_read():
    # A declared Content-Length beyond the ceiling is refused outright — the exact
    # DoS the middleware exists for (a 2 GB POST never gets buffered).
    async with _client(_app()) as ac:
        resp = await ac.post("/echo", content=b"x" * (_MAX + 50))
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "PayloadTooLargeError"


@pytest.mark.asyncio
async def test_chunked_oversized_body_rejected_by_running_count():
    # No Content-Length (chunked upload): the running byte count trips the limit and
    # raises PayloadTooLargeError (mapped to 413), stopping any further reads.
    async def gen():
        for _ in range(4):
            yield b"x" * 40  # 160 bytes total > 100

    async with _client(_app()) as ac:
        resp = await ac.post("/echo", content=gen())
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "PayloadTooLargeError"


@pytest.mark.asyncio
async def test_body_exactly_at_limit_passes():
    async with _client(_app()) as ac:
        resp = await ac.post("/echo", content=b"x" * _MAX)
    assert resp.status_code == 200
    assert resp.json() == {"len": _MAX}
