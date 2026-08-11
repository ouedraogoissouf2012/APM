import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from pwdlib import PasswordHash

from app.config import get_settings

_pwd = PasswordHash.recommended()


def generate_refresh_token() -> str:
    """A high-entropy opaque refresh token (the raw value is returned to the client once)."""
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    """Hash a refresh token for storage — we never persist the raw value (SHA-256)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class InvalidTokenError(Exception):
    pass


def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


def create_dummy_password_hash() -> str:
    """Create a realistic dummy hash for timing-attack resistance (#239).

    When a user doesn't exist, we still call verify_password with this dummy hash
    to equalize timing between 'email not found' (~1ms) and 'password invalid' (~50ms).
    """
    return hash_password(secrets.token_urlsafe(32))


def create_access_token(subject: str) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    # jti enables token revocation (#239)
    payload = {"sub": subject, "exp": expire, "jti": str(uuid4())}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    subject = payload.get("sub")
    if subject is None:
        raise InvalidTokenError("missing subject")
    return subject
