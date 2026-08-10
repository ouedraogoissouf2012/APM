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
    *,
    namespace: str,
    max_hits: int,
    window_seconds: int,
    redis_url: str,
    max_keys: int = 1000,
) -> RateLimiter:
    """Build a rate limiter backend from config.

    If redis_url is empty, returns InMemoryRateLimiter (dev/test only, single worker).
    In production (multi-worker uvicorn), set REDIS_URL to share limits across instances.

    Args:
        namespace: Namespace for the rate limit keys (e.g., "login", "conversation").
        max_hits: Max attempts within the window before limiting.
        window_seconds: Time window duration.
        redis_url: Redis URL (empty → in-memory, single-process).
        max_keys: Max entries in the in-memory dict (prevents DoS via high-cardinality keys).
    """
    if not redis_url.strip():
        return InMemoryRateLimiter(
            max_hits=max_hits, window_seconds=window_seconds, max_keys=max_keys
        )
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
