import logging
import os
import time

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.rate_limit import InMemoryRateLimiter, RedisRateLimiter, user_rate_limit_key
from app.domain.exceptions import RateLimitedError


def test_user_rate_limit_key_has_no_ip_component():
    """#356: every paid-provider endpoint builds its limiter key through this
    function so the key is user_id-only — no caller can slip an IP back in."""
    assert user_rate_limit_key("tts", 42) == "tts:user:42"
    # Same user, different namespace -> different bucket (no cross-endpoint bleed).
    assert user_rate_limit_key("mission", 42) != user_rate_limit_key("tts", 42)


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


@pytest.mark.asyncio
async def test_evicts_empty_buckets_on_window_expiry():
    """Buckets with no hits are removed from the dict (cleanup stale entries #234)."""
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


class _FakeScript:
    """Mimics `Redis.register_script()`'s callable: the atomic INCR+EXPIRE Lua
    script run via EVALSHA. Increments the counter, and records a TTL only the
    first time a key is seen — same behavior a real Redis server gives when
    running the script."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.expired: dict[str, int] = {}

    async def __call__(self, keys: list[str] | None = None, args: list[str] | None = None) -> int:
        key = (keys or [""])[0]
        ttl_seconds = int((args or ["0"])[0])
        self.counts[key] = self.counts.get(key, 0) + 1
        if self.counts[key] == 1:
            self.expired[key] = ttl_seconds
        return self.counts[key]


class _FailingScript:
    """Simulates a Redis outage/timeout: every call raises a redis-py error —
    the same exception type RedisRateLimiter narrows its handling to."""

    async def __call__(self, keys: list[str] | None = None, args: list[str] | None = None) -> int:
        raise RedisConnectionError("connection refused")


@pytest.mark.asyncio
async def test_redis_rate_limiter_uses_shared_script_counters():
    script = _FakeScript()
    limiter = RedisRateLimiter(script, namespace="auth", max_hits=1, window_seconds=60)

    await limiter.check("ip:user")

    with pytest.raises(RateLimitedError):
        await limiter.check("ip:user")
    assert list(script.expired.values()) == [61]


@pytest.mark.asyncio
async def test_redis_rate_limiter_builds_namespaced_bucketed_key():
    """The Redis key mixes namespace + fixed window bucket + the caller's key,
    so different endpoints (namespaces) never share a counter."""
    script = _FakeScript()
    limiter = RedisRateLimiter(script, namespace="auth", max_hits=5, window_seconds=60)

    await limiter.check("ip:1.2.3.4")

    (constructed_key,) = script.counts.keys()
    assert constructed_key.startswith("rate:auth:")
    assert constructed_key.endswith(":ip:1.2.3.4")


@pytest.mark.asyncio
async def test_redis_rate_limiter_different_keys_get_independent_counters():
    script = _FakeScript()
    limiter = RedisRateLimiter(script, namespace="auth", max_hits=1, window_seconds=60)

    await limiter.check("ip:a")
    await limiter.check("ip:b")  # different key, independent counter

    with pytest.raises(RateLimitedError):
        await limiter.check("ip:a")


@pytest.mark.asyncio
async def test_redis_rate_limiter_fails_open_by_default_when_redis_is_unavailable():
    """A Redis outage must not turn into a 500 on every rate-limited route
    (#234): the request is allowed through, not blocked, by default."""
    limiter = RedisRateLimiter(_FailingScript(), namespace="auth", max_hits=1, window_seconds=60)

    await limiter.check("ip:user")  # does not raise despite Redis being down


@pytest.mark.asyncio
async def test_redis_rate_limiter_fails_closed_when_configured():
    """Security-sensitive routes (login/register/refresh) opt into
    fail_open=False (#234): an unreachable limiter must not hand out
    unlimited attempts during an outage — treated as rate-limited instead."""
    limiter = RedisRateLimiter(
        _FailingScript(), namespace="login", max_hits=1, window_seconds=60, fail_open=False
    )

    with pytest.raises(RateLimitedError):
        await limiter.check("ip:user")


@pytest.mark.asyncio
async def test_redis_rate_limiter_throttles_failure_logging(caplog):
    """A sustained outage must not flood logs with one warning per request
    (#234): repeated failures within the throttle window log once."""
    limiter = RedisRateLimiter(_FailingScript(), namespace="auth", max_hits=1, window_seconds=60)

    with caplog.at_level(logging.WARNING, logger="app.core.rate_limit"):
        await limiter.check("ip:a")
        await limiter.check("ip:b")

    assert len(caplog.records) == 1


class _SpyRedisClient:
    """Mimics redis.asyncio.Redis's async `aclose()`."""

    def __init__(self) -> None:
        self.closed = 0

    async def aclose(self) -> None:
        self.closed += 1


@pytest.mark.asyncio
async def test_redis_rate_limiter_aclose_closes_its_client():
    """#303: the Redis client passed at construction is what shutdown closes."""
    client = _SpyRedisClient()
    limiter = RedisRateLimiter(
        _FakeScript(), namespace="auth", max_hits=1, window_seconds=60, client=client
    )

    await limiter.aclose()

    assert client.closed == 1


@pytest.mark.asyncio
async def test_redis_rate_limiter_aclose_is_a_noop_without_a_client():
    """Constructing a limiter from a bare script fake (no `client=`, as every
    other test in this file does) must not make aclose() blow up."""
    limiter = RedisRateLimiter(_FakeScript(), namespace="auth", max_hits=1, window_seconds=60)

    await limiter.aclose()  # must not raise


@pytest.mark.skipif(
    not os.environ.get("REDIS_URL"), reason="requires a live Redis server (set REDIS_URL)"
)
@pytest.mark.asyncio
async def test_redis_rate_limiter_against_real_redis():
    """Opt-in integration test: exercises the ACTUAL Lua script against a real
    Redis server. The unit tests above use a Python fake that hand-replicates
    the script's intended semantics and can't catch a real Lua syntax/logic
    bug in `_INCR_AND_EXPIRE_SCRIPT`. Skipped unless REDIS_URL is set, so CI
    without a Redis service stays green; a stage with Redis available gets
    real coverage of the script itself."""
    from app.core.rate_limit_factory import build_rate_limiter

    limiter = build_rate_limiter(
        namespace=f"test-{time.time_ns()}",
        max_hits=2,
        window_seconds=5,
        redis_url=os.environ["REDIS_URL"],
    )
    await limiter.check("k")
    await limiter.check("k")
    with pytest.raises(RateLimitedError):
        await limiter.check("k")
