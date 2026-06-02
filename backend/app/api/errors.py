"""Central mapping of domain exceptions to HTTP responses.

Registered once on the app. Keeps services/routes free of HTTP status concerns
and guarantees a single, normalized error body: {"error": {"code", "message"}}.
"""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.domain.exceptions import (
    AuthenticationError,
    ConflictError,
    DomainError,
    InvalidCredentialsError,
    NotFoundError,
    QuotaExhaustedError,
)

# Most specific first; a base DomainError fallback catches anything unmapped.
_STATUS_BY_EXCEPTION: list[tuple[type[DomainError], int]] = [
    (AuthenticationError, status.HTTP_401_UNAUTHORIZED),
    (InvalidCredentialsError, status.HTTP_401_UNAUTHORIZED),
    (NotFoundError, status.HTTP_404_NOT_FOUND),
    (QuotaExhaustedError, status.HTTP_402_PAYMENT_REQUIRED),
    (ConflictError, status.HTTP_409_CONFLICT),
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


def register_exception_handlers(app: FastAPI) -> None:
    for exc_type, http_status in _STATUS_BY_EXCEPTION:
        app.add_exception_handler(exc_type, _make_handler(http_status))
