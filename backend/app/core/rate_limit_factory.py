"""Select a rate-limiter backend from configuration (#120).

`RedisRateLimiter` existed but was never wired — every module built the in-memory
one, so limits never held across instances. This factory picks the backend from
`redis_url`: empty -> in-memory (single process, dev/tests, no Redis dependency);
set -> a Redis-backed limiter shared across all app instances. Callers depend on
the `RateLimiter` interface, so nothing above changes when the backend does.
"""

from typing import cast

from app.core.rate_limit import (
    _INCR_AND_EXPIRE_SCRIPT,
    InMemoryRateLimiter,
    RateLimiter,
    RedisRateLimiter,
    RedisScript,
)


def build_rate_limiter(
    *,
    namespace: str,
    max_hits: int,
    window_seconds: int,
    redis_url: str,
    max_keys: int = 1000,
    fail_open: bool = True,
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
        fail_open: When Redis is unreachable, allow the request through (True, the
            default — availability over strict limiting everywhere else) instead of
            rejecting it as rate-limited (False — for security-sensitive routes like
            login/register/refresh, where an unverifiable limiter must not hand out
            unlimited attempts). Ignored in in-memory mode (no network call to fail).
    """
    if not redis_url.strip():
        return InMemoryRateLimiter(
            max_hits=max_hits, window_seconds=window_seconds, max_keys=max_keys
        )
    # Import redis lazily so dev/test installs that never set REDIS_URL don't pay
    # for constructing a client (connection pool setup) they'll never use.
    from redis.asyncio import Redis

    client = Redis.from_url(redis_url)
    # register_script() runs the script via EVALSHA (just a hash over the wire),
    # transparently falling back to EVAL (which also caches it) the first time or
    # after a cache flush — so the full Lua body is sent once per Redis node, not
    # on every check(). Its actual return type is broader than our minimal
    # RedisScript contract, so cast to what RedisRateLimiter actually uses.
    script = cast(RedisScript, client.register_script(_INCR_AND_EXPIRE_SCRIPT))
    return RedisRateLimiter(
        script,
        namespace=namespace,
        max_hits=max_hits,
        window_seconds=window_seconds,
        fail_open=fail_open,
    )
