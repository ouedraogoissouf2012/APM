import pytest

from app.core.rate_limit import InMemoryRateLimiter
from app.domain.exceptions import RateLimitedError


@pytest.mark.asyncio
async def test_allows_up_to_max_then_blocks():
    limiter = InMemoryRateLimiter(max_hits=3, window_seconds=60)
    for _ in range(3):
        await limiter.check("k")  # 3 allowed
    with pytest.raises(RateLimitedError):
        await limiter.check("k")  # 4th blocked


@pytest.mark.asyncio
async def test_keys_are_independent():
    limiter = InMemoryRateLimiter(max_hits=1, window_seconds=60)
    await limiter.check("a")
    await limiter.check("b")  # different key, still allowed
    with pytest.raises(RateLimitedError):
        await limiter.check("a")
