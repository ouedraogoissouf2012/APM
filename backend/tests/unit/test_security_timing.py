"""Login timing-attack guard (#239): the dummy password hash must be PRECOMPUTED,
not re-hashed on every non-existent-email login — re-hashing would add a second
argon2 op to each miss, making a miss ~2x slower and re-opening the timing oracle
the guard exists to close.
"""

import asyncio

import pytest

from app.core.security import dummy_password_hash, verify_password


@pytest.mark.asyncio
async def test_dummy_password_hash_is_computed_once_and_reused():
    # Same string every call → cached (computed once), never re-hashed per miss.
    assert await dummy_password_hash() == await dummy_password_hash()


@pytest.mark.asyncio
async def test_dummy_password_hash_is_a_real_argon2_hash():
    # It must be a genuine argon2 hash so verifying against it has the SAME cost as
    # verifying a real user's password — that equal cost is the whole point.
    h = await dummy_password_hash()
    assert "argon2" in h
    assert await verify_password("anything", h) is False  # a random secret → never matches


@pytest.mark.asyncio
async def test_dummy_password_hash_is_race_safe_under_concurrent_first_calls():
    """#386: the cache switched from @lru_cache (sync, single-flight by the GIL
    around the call) to manual double-checked locking (needed because
    hash_password is now async). Two concurrent FIRST calls must still settle
    on the SAME hash, not each compute and briefly use a different one."""
    import app.core.security as security_module

    security_module._dummy_hash = None  # force the "never computed yet" path

    results = await asyncio.gather(*(dummy_password_hash() for _ in range(8)))

    assert len(set(results)) == 1
