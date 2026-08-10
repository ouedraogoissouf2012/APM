"""Central mapping of domain exceptions to HTTP responses.

Registered once on the app. Keeps services/routes free of HTTP status concerns
and guarantees a single, normalized error body: {"error": {"code", "message"}}.
"""

import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError

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
        headers = {}
        if http_status == status.HTTP_401_UNAUTHORIZED:
            headers["WWW-Authenticate"] = "Bearer"  # RFC 6750
        elif http_status == status.HTTP_429_TOO_MANY_REQUESTS:
            headers["Retry-After"] = "60"  # Retry after 60 seconds
        return JSONResponse(
            status_code=http_status,
            content={"error": {"code": exc.__class__.__name__, "message": message}},
            headers=headers,
        )

    return handler


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Anything not a mapped DomainError is a bug, not an expected 4xx: log it with
    the stack + the request's correlation id, and return the SAME normalized
    envelope as every other error — never a bare Starlette 'Internal Server Error'
    that leaves nothing to trace (#235).

    This runs in the OUTERMOST ServerErrorMiddleware, after RequestContextMiddleware
    has already reset the request-id contextvar as the exception unwound. So we read
    the id from the ASGI scope (which survives), pass it to the log explicitly, and
    echo it on the response so a user can quote it (#257)."""
    request_id = request.scope.get("apm_request_id", "-")
    _logger.error(
        "Unhandled exception: %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
        extra={"request_id": request_id},
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"code": "InternalServerError", "message": "Internal server error"}},
        headers={"X-Request-ID": request_id},
    )


async def _data_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """SQLAlchemy DataError (e.g., constraint violation, value out of range).
    Mapped to 422 since it indicates invalid input — likely a client sending data
    that bypassed Pydantic validation or a pre-check."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": {"code": "DataError", "message": "Invalid input"}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    for exc_type, http_status in _STATUS_BY_EXCEPTION:
        app.add_exception_handler(exc_type, _make_handler(http_status))
    app.add_exception_handler(DataError, _data_error_handler)
    # Catch-all for unmapped exceptions (bugs): logged + normalized 500.
    app.add_exception_handler(Exception, _unhandled_exception_handler)
