import asyncio
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


async def hash_password(plain: str) -> str:
    # argon2 (RFC 9106 recommended params: t=3, m=64MiB) is deliberately expensive —
    # ~50-150ms of pure CPU. Run off the event loop (#386): inline, it blocks every
    # other coroutine on this worker (incl. concurrent SSE turn streaming) for its
    # full duration.
    return await asyncio.to_thread(_pwd.hash, plain)


async def verify_password(plain: str, hashed: str) -> bool:
    return await asyncio.to_thread(_pwd.verify, plain, hashed)


_dummy_hash: str | None = None
_dummy_hash_lock = asyncio.Lock()


async def dummy_password_hash() -> str:
    """A STABLE dummy hash, computed ONCE, for login timing-attack resistance (#239).

    On a non-existent email, login still runs verify_password against this hash, so a
    miss costs exactly ONE argon2 verify — the same as a real user. It is precomputed
    (cached), NOT re-hashed per call: re-hashing would add a second argon2 op to every
    miss, making a non-existent email ~2x slower and re-opening the very timing oracle
    this closes.

    Manual double-checked-locking cache, not @lru_cache (#386): hash_password is now
    async, and lru_cache would cache the CORO OBJECT itself — awaitable only once —
    not its result, breaking on the second call. The lock also closes a startup race:
    without it, two concurrent first-ever misses could each compute (and briefly use)
    a DIFFERENT dummy hash before the cache settles.
    """
    global _dummy_hash
    if _dummy_hash is None:
        async with _dummy_hash_lock:
            if _dummy_hash is None:
                _dummy_hash = await hash_password(secrets.token_urlsafe(32))
    return _dummy_hash


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
