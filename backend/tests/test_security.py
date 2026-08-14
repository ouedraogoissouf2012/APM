import asyncio

import pytest

from app.core import security


@pytest.mark.asyncio
async def test_password_hash_roundtrip():
    hashed = await security.hash_password("s3cret!pass")
    assert hashed != "s3cret!pass"
    assert await security.verify_password("s3cret!pass", hashed) is True
    assert await security.verify_password("wrong", hashed) is False


@pytest.mark.asyncio
async def test_hash_password_does_not_block_the_event_loop():
    """#386: argon2 hashing is a deliberately expensive (~50-150ms) CPU-bound
    call. Run inline on the loop it would freeze every other coroutine (incl.
    concurrent SSE turn streaming) for its full duration — it must be offloaded
    to a thread instead. Proof: a concurrent 'ticker' coroutine must keep making
    progress WHILE the hash is computing, not just before/after it."""
    ticks = 0
    stop = False

    async def _ticker() -> None:
        nonlocal ticks
        while not stop:
            ticks += 1
            await asyncio.sleep(0)  # yield back to the loop on every iteration

    ticker_task = asyncio.create_task(_ticker())
    await asyncio.sleep(0)  # let the ticker run at least once before the hash starts

    await security.hash_password("s3cret!pass")

    stop = True
    await ticker_task

    # A blocking (non-offloaded) hash would let the ticker advance ZERO times
    # DURING the ~50-150ms argon2 call — the whole call would run as one
    # uninterrupted step on the loop's single thread. A genuinely offloaded
    # hash lets the ticker interleave many times while the thread works.
    assert ticks > 5, f"event loop appears blocked during hash_password (ticks={ticks})"


def test_jwt_roundtrip():
    token = security.create_access_token(subject="42")
    assert security.decode_access_token(token) == "42"


def test_jwt_rejects_tampered_token():
    token = security.create_access_token(subject="42")
    with pytest.raises(security.InvalidTokenError):
        security.decode_access_token(token + "x")
