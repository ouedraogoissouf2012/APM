"""Central mapping of domain exceptions to HTTP responses.

Registered once on the app. Keeps services/routes free of HTTP status concerns
and guarantees a single, normalized error body: {"error": {"code", "message"}}.
"""

import http
import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

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


def _error_response(
    http_status: int, code: str, message: str, *, headers: dict[str, str] | None = None
) -> JSONResponse:
    """The one place that builds the normalized error body — every handler below
    goes through this so {"error": {"code", "message"}} cannot drift into a
    per-handler ad-hoc shape."""
    return JSONResponse(
        status_code=http_status,
        content={"error": {"code": code, "message": message}},
        headers=headers,
    )


def _make_handler(http_status: int) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        message = getattr(exc, "message", "") or str(exc)
        headers = {}
        if http_status == status.HTTP_401_UNAUTHORIZED:
            headers["WWW-Authenticate"] = "Bearer"  # RFC 6750
        elif http_status == status.HTTP_429_TOO_MANY_REQUESTS:
            headers["Retry-After"] = "60"  # Retry after 60 seconds
        if http_status >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            # A DomainError mapped to 5xx (LlmProviderError/DebriefAnalysisError ->
            # 502) is an external dependency failure, not an expected client
            # outcome like the 4xx branches above — log it with the stack so an
            # STT/debrief/mission outage is root-causable from logs alone (#402).
            _log_server_side(request, exc)
        return _error_response(http_status, exc.__class__.__name__, message, headers=headers)

    return handler


def _log_server_side(request: Request, exc: Exception) -> None:
    _logger.warning(
        "Domain 5xx: %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
        extra={"request_id": request.scope.get("apm_request_id", "-")},
    )


def _log_db_constraint_error(request: Request, exc: Exception) -> None:
    # A surprising DataError/IntegrityError is worth a WARNING (the upstream Pydantic
    # validation or ON CONFLICT that should have caught it didn't) — but log it WITHOUT
    # exc_info/str(exc). A SQLAlchemy DB error renders the driver's DETAIL, which for a
    # unique violation carries the CONFLICTING VALUE (e.g. "Key (email)=(alice@x.com)
    # already exists"); that is NOT hidden by the engine's hide_parameters (which only
    # suppresses the bound-parameters section) and must never land in logs. The class
    # name + method + path + request_id pinpoint the surprise without leaking learner data.
    _logger.warning(
        "DB constraint error (%s): %s %s",
        exc.__class__.__name__,
        request.method,
        request.url.path,
        extra={"request_id": request.scope.get("apm_request_id", "-")},
    )


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
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "InternalServerError",
        "Internal server error",
        headers={"X-Request-ID": request_id},
    )


async def _data_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """SQLAlchemy DataError (e.g., constraint violation, value out of range).
    Mapped to 422 since it indicates invalid input — likely a client sending data
    that bypassed Pydantic validation or a pre-check. Despite the 4xx response,
    reaching this net is itself a surprise (validation that should have caught it
    upstream didn't), so it's logged (value-free) as a surprising conflict (#402)."""
    _log_db_constraint_error(request, exc)
    return _error_response(status.HTTP_422_UNPROCESSABLE_ENTITY, "DataError", "Invalid input")


async def _integrity_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """SQLAlchemy IntegrityError — a unique/foreign-key/check constraint violation
    that reached the DB uncaught (#362). Most get-or-create races are already
    closed at the repository level with an ON CONFLICT clause, but this is the
    safety net for any commit that isn't: mapped to 409 (the request conflicts
    with the current state) rather than falling through to a raw 500. That
    safety net firing is by definition a surprise disguised as a routine
    conflict, so it's logged (value-free) as a surprising conflict (#402)."""
    _log_db_constraint_error(request, exc)
    return _error_response(status.HTTP_409_CONFLICT, "IntegrityError", "Conflicting data")


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """FastAPI/Starlette's built-in HTTPException, raised ad hoc across routers for
    one-off checks (e.g. a 403 consent gate, a 422 pre-check) — AND the one Starlette's
    own router raises directly for an unmatched route (404) or wrong method (405).
    Without this, both fall back to Starlette's default {"detail": ...} body — a second,
    incompatible error shape next to every DomainError's {"error": {"code", "message"}}.

    Registered under starlette.exceptions.HTTPException (not fastapi.HTTPException, a
    subclass of it) so it also catches the router-raised 404/405: Starlette dispatches
    by walking the exception's MRO for the first registered ancestor, and a plain
    starlette.exceptions.HTTPException's MRO does not include the fastapi subclass.

    Typed as the base Exception (not HTTPException) because Starlette requires every
    registered handler to accept Exception — it dispatches by the exact class it was
    registered under, so this only ever runs for an HTTPException in practice."""
    detail = getattr(exc, "detail", "")
    message = detail if isinstance(detail, str) else str(detail)
    exc_status = getattr(exc, "status_code", status.HTTP_500_INTERNAL_SERVER_ERROR)
    try:
        code = http.HTTPStatus(exc_status).phrase.replace(" ", "")
    except ValueError:
        code = "HTTPException"
    return _error_response(exc_status, code, message, headers=getattr(exc, "headers", None))


def _validation_field_message(err: dict) -> str:
    location = ".".join(str(part) for part in err["loc"] if part != "body")
    return f"{location}: {err['msg']}" if location else str(err["msg"])


async def _validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """A request body/query/path field that fails Pydantic validation (e.g.
    native_language over its max length). FastAPI's default handler returns
    {"detail": [...]} — normalized here to the same envelope as every other error."""
    errors = exc.errors() if isinstance(exc, RequestValidationError) else []
    message = "; ".join(_validation_field_message(err) for err in errors)
    return _error_response(status.HTTP_422_UNPROCESSABLE_ENTITY, "ValidationError", message)


def register_exception_handlers(app: FastAPI) -> None:
    for exc_type, http_status in _STATUS_BY_EXCEPTION:
        app.add_exception_handler(exc_type, _make_handler(http_status))
    app.add_exception_handler(DataError, _data_error_handler)
    app.add_exception_handler(IntegrityError, _integrity_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    # Catch-all for unmapped exceptions (bugs): logged + normalized 500.
    app.add_exception_handler(Exception, _unhandled_exception_handler)
