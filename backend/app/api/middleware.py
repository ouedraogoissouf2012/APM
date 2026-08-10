"""HTTP middleware: per-request id, access logging, and security headers.

Implemented as a PURE ASGI middleware (not Starlette's BaseHTTPMiddleware) on
purpose: BaseHTTPMiddleware buffers the ENTIRE response body before returning it,
which stalls streaming responses (SSE) — the conversation's token stream would be
held back ~2-3 s and released all at once. A pure ASGI middleware forwards each
chunk as it is produced, so the first spoken sentence reaches the client the
moment it is generated.
"""

import logging
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import request_id_var
from app.domain.exceptions import PayloadTooLargeError

_logger = logging.getLogger("apm.request")


class BodySizeLimitMiddleware:
    """Rejects a request whose body exceeds [max_bytes] with 413 BEFORE it is
    buffered into memory (#221).

    Starlette reads the ENTIRE request body into memory before Pydantic validation,
    so without this an unauthenticated POST with a multi-GB body would OOM the
    worker (a field's `max_length` caps the parsed string, never the bytes read).
    Two guards: a fast reject on a declared oversized `Content-Length`, and — for
    chunked or lying `Content-Length` — a running byte count that raises
    [PayloadTooLargeError] once the ceiling is passed (mapped to 413 centrally),
    which also stops the app from reading any further, bounding memory.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self._app = app
        self._max = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        declared = Headers(scope=scope).get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > self._max:
            await _send_413(send)
            return

        seen = 0

        async def counting_receive() -> Message:
            nonlocal seen
            message = await receive()
            if message.get("type") == "http.request":
                seen += len(message.get("body", b""))
                if seen > self._max:
                    raise PayloadTooLargeError("Request body too large")
            return message

        await self._app(scope, counting_receive, send)


async def _send_413(send: Send) -> None:
    body = b'{"error":{"code":"PayloadTooLargeError","message":"Request body too large"}}'
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'none'; "
        "base-uri 'none'; "
        "frame-ancestors 'none'; "
        "form-action 'self'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'"
    ),
    "Permissions-Policy": (
        "accelerometer=(), ambient-light-sensor=(), autoplay=(), battery=(), "
        "camera=(), display-capture=(), document-domain=(), encrypted-media=(), "
        "fullscreen=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), "
        "midi=(), payment=(), picture-in-picture=(), publickey-credentials-get=(), "
        "screen-wake-lock=(), sync-xhr=(), usb=(), web-share=(), xr-spatial-tracking=()"
    ),
}
_HSTS_HEADER = "max-age=63072000; includeSubDomains; preload"


class RequestContextMiddleware:
    """Assigns a request id, logs one structured line per request, sets security
    headers — WITHOUT buffering the response (so SSE streams immediately)."""

    def __init__(self, app: ASGIApp, *, enable_hsts: bool = False) -> None:
        self._app = app
        self._enable_hsts = enable_hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_headers = Headers(scope=scope)
        request_id = request_headers.get("X-Request-ID") or uuid.uuid4().hex
        # Expose the id to every log emitted while handling this request (#235), so an
        # error deep in the app correlates to its request. Reset after, to not leak.
        token = request_id_var.set(request_id)
        start = time.monotonic()
        status_code = 500  # default if the app never sends a start message

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                for header, value in _SECURITY_HEADERS.items():
                    if header not in headers:
                        headers[header] = value
                if self._enable_hsts and _is_https(scope, request_headers):
                    headers.setdefault("Strict-Transport-Security", _HSTS_HEADER)
                # Log once, at response start — never waits for the body to finish,
                # so a long-lived SSE stream is logged when it opens, not when it ends.
                _logger.info(
                    "request",
                    extra={
                        "request_id": request_id,
                        "method": scope.get("method", ""),
                        "path": scope.get("path", ""),
                        "status": status_code,
                        "duration_ms": round((time.monotonic() - start) * 1000, 1),
                    },
                )
            await send(message)

        try:
            await self._app(scope, receive, send_wrapper)
        finally:
            request_id_var.reset(token)


def _is_https(scope: Scope, headers: Headers) -> bool:
    forwarded_proto = headers.get("X-Forwarded-Proto", "")
    scheme = scope.get("scheme", "")
    return scheme == "https" or forwarded_proto.lower().split(",")[0].strip() == "https"
