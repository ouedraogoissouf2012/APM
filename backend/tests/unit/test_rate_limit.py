import pytest

from app.core.rate_limit import InMemoryRateLimiter, RedisRateLimiter
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


class _FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.expired: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> object:
        self.expired[key] = seconds
        return True


@pytest.mark.asyncio
async def test_redis_rate_limiter_uses_shared_client_counters():
    redis = _FakeRedis()
    limiter = RedisRateLimiter(redis, namespace="auth", max_hits=1, window_seconds=60)

    await limiter.check("ip:user")

    with pytest.raises(RateLimitedError):
        await limiter.check("ip:user")
    assert list(redis.expired.values()) == [61]
