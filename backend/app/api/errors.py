"""Central mapping of domain exceptions to HTTP responses.

Registered once on the app. Keeps services/routes free of HTTP status concerns
and guarantees a single, normalized error body: {"error": {"code", "message"}}.
"""

import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.domain.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    DebriefAnalysisError,
    DomainError,
    InvalidCredentialsError,
    LlmProviderError,
    NotFoundError,
    PayloadTooLargeError,
    QuotaExhaustedError,
    RateLimitedError,
)

_logger = logging.getLogger("apm.error")

# Most specific first; a base DomainError fallback catches anything unmapped.
_STATUS_BY_EXCEPTION: list[tuple[type[DomainError], int]] = [
    (AuthenticationError, status.HTTP_401_UNAUTHORIZED),
    (InvalidCredentialsError, status.HTTP_401_UNAUTHORIZED),
    (AuthorizationError, status.HTTP_403_FORBIDDEN),
    (NotFoundError, status.HTTP_404_NOT_FOUND),
    (QuotaExhaustedError, status.HTTP_402_PAYMENT_REQUIRED),
    (RateLimitedError, status.HTTP_429_TOO_MANY_REQUESTS),
    (PayloadTooLargeError, status.HTTP_413_CONTENT_TOO_LARGE),
    (ConflictError, status.HTTP_409_CONFLICT),
    (DebriefAnalysisError, status.HTTP_502_BAD_GATEWAY),
    (LlmProviderError, status.HTTP_502_BAD_GATEWAY),
    (DomainError, status.HTTP_400_BAD_REQUEST),
]


def _make_handler(http_status: int) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        message = getattr(exc, "message", "") or str(exc)
        return JSONResponse(
            status_code=http_status,
            content={"error": {"code": exc.__class__.__name__, "message": message}},
        )

    return handler


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Anything not a mapped DomainError is a bug, not an expected 4xx: log it with
    the stack + the request's correlation id (via the log filter), and return the
    SAME normalized envelope as every other error — never a bare Starlette
    'Internal Server Error' that leaves nothing to trace (#235)."""
    _logger.error("Unhandled exception: %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"code": "InternalServerError", "message": "Internal server error"}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    for exc_type, http_status in _STATUS_BY_EXCEPTION:
        app.add_exception_handler(exc_type, _make_handler(http_status))
    # Catch-all for unmapped exceptions (bugs): logged + normalized 500.
    app.add_exception_handler(Exception, _unhandled_exception_handler)
