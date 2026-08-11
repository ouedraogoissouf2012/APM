import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache
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


@lru_cache(maxsize=1)
def dummy_password_hash() -> str:
    """A STABLE dummy hash, computed ONCE, for login timing-attack resistance (#239).

    On a non-existent email, login still runs verify_password against this hash, so a
    miss costs exactly ONE argon2 verify — the same as a real user. It is precomputed
    (cached), NOT re-hashed per call: re-hashing would add a second argon2 op to every
    miss, making a non-existent email ~2x slower and re-opening the very timing oracle
    this closes.
    """
    return hash_password(secrets.token_urlsafe(32))


def create_access_token(subject: str) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    # A unique token id: makes each access token identifiable in logs and is the
    # groundwork for a future denylist-based revocation. NOT yet enforced (no
    # revocation check exists today) — traceability + groundwork, not live
    # revocation (#239).
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
