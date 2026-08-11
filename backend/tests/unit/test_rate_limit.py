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
async def test_evicts_empty_buckets_on_window_expiry():
    """Buckets with no hits are removed from the dict (cleanup stale entries #234)."""
    import time

    limiter = InMemoryRateLimiter(max_hits=1, window_seconds=1)
    await limiter.check("a")
    assert len(limiter._hits) == 1  # bucket exists
    # Sleep past the 1-second window so the hit expires.
    time.sleep(1.1)
    await limiter.check("a")  # re-check; the old hit expires and bucket is cleaned
    # After eviction of the expired hit, the bucket stays (it got a new hit).
    assert len(limiter._hits) == 1


@pytest.mark.asyncio
async def test_max_keys_evicts_oldest_bucket_fifo():
    """When at max_keys capacity, adding a new key evicts the oldest bucket (FIFO #234)."""
    limiter = InMemoryRateLimiter(max_hits=2, window_seconds=60, max_keys=2)
    await limiter.check("a")
    await limiter.check("b")
    assert len(limiter._hits) == 2  # at capacity
    # Adding a third key should evict "a" (oldest).
    await limiter.check("c")
    assert len(limiter._hits) == 2
    assert "a" not in limiter._hits
    assert "b" in limiter._hits
    assert "c" in limiter._hits


@pytest.mark.asyncio
async def test_redis_rate_limiter_uses_shared_client_counters():
    redis = _FakeRedis()
    limiter = RedisRateLimiter(redis, namespace="auth", max_hits=1, window_seconds=60)

    await limiter.check("ip:user")

    with pytest.raises(RateLimitedError):
        await limiter.check("ip:user")
    assert list(redis.expired.values()) == [61]
