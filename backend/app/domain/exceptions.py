"""Domain/business exceptions.

Services raise these — never HTTPException. The API layer maps them to HTTP
status codes centrally (see app/api/errors.py). This keeps business logic free
of any web-framework dependency (SRP / clean dependency direction).
"""


class DomainError(Exception):
    """Base class for all business/domain errors."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    """A requested resource does not exist."""


class ConflictError(DomainError):
    """The operation conflicts with the current state (e.g. uniqueness)."""


class EmailAlreadyExistsError(ConflictError):
    """Registration attempted with an email that is already taken."""


class InvalidCredentialsError(DomainError):
    """Login failed: unknown email or wrong password."""


class AuthenticationError(DomainError):
    """The caller is not authenticated (missing/invalid token, unknown user)."""
