"""Select a rate-limiter backend from configuration (#120).

`RedisRateLimiter` existed but was never wired — every module built the in-memory
one, so limits never held across instances. This factory picks the backend from
`redis_url`: empty -> in-memory (single process, dev/tests, no Redis dependency);
set -> a Redis-backed limiter shared across all app instances. Callers depend on
the `RateLimiter` interface, so nothing above changes when the backend does.
"""

from typing import cast

from app.core.rate_limit import (
    InMemoryRateLimiter,
    RateLimiter,
    RedisRateLimitClient,
    RedisRateLimiter,
)


def build_rate_limiter(
    *, namespace: str, max_hits: int, window_seconds: int, redis_url: str
) -> RateLimiter:
    if not redis_url.strip():
        return InMemoryRateLimiter(max_hits=max_hits, window_seconds=window_seconds)
    # Import redis lazily so dev/test installs need no Redis dependency.
    from redis.asyncio import Redis

    # redis-py's async client provides incr(key) and expire(key, seconds) callable
    # positionally, satisfying RedisRateLimitClient; its stub signatures are wider
    # (extra kwargs), so cast to the minimal contract we actually use.
    client = cast(RedisRateLimitClient, Redis.from_url(redis_url))
    return RedisRateLimiter(
        client=client,
        namespace=namespace,
        max_hits=max_hits,
        window_seconds=window_seconds,
    )
