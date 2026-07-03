"""HTTP middleware: per-request id, access logging, and security headers."""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

_logger = logging.getLogger("apm.request")

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


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, logs one structured line per request, sets headers."""

    def __init__(self, app: ASGIApp, *, enable_hsts: bool = False) -> None:
        super().__init__(app)
        self._enable_hsts = enable_hsts

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 1)

        _logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )

        response.headers["X-Request-ID"] = request_id
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if self._enable_hsts and _is_https(request):
            response.headers.setdefault("Strict-Transport-Security", _HSTS_HEADER)
        return response


def _is_https(request: Request) -> bool:
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "")
    return request.url.scheme == "https" or forwarded_proto.lower().split(",")[0].strip() == "https"
