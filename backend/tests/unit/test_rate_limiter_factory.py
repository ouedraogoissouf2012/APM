"""Unit tests for the rate-limiter factory (#120).

The RedisRateLimiter existed but nothing built it — every module hard-coded the
in-memory one. The factory selects the backend from config (redis_url) so a
multi-instance deployment gets cross-process limiting, while dev/tests stay
in-memory with no Redis dependency.
"""

import pytest

from app.core import http_lifecycle
from app.core.rate_limit import InMemoryRateLimiter, RedisRateLimiter
from app.core.rate_limit_factory import build_rate_limiter


def test_builds_in_memory_when_no_redis_url():
    limiter = build_rate_limiter(namespace="login", max_hits=5, window_seconds=60, redis_url="")
    assert isinstance(limiter, InMemoryRateLimiter)


def test_builds_redis_when_url_is_set():
    limiter = build_rate_limiter(
        namespace="login", max_hits=5, window_seconds=60, redis_url="redis://localhost:6379/0"
    )
    assert isinstance(limiter, RedisRateLimiter)


def test_redis_limiter_carries_namespace_and_limits():
    limiter = build_rate_limiter(
        namespace="turn", max_hits=7, window_seconds=30, redis_url="redis://localhost:6379/0"
    )
    assert isinstance(limiter, RedisRateLimiter)
    # Namespaced so different endpoints don't share buckets.
    assert limiter._namespace == "turn"
    assert limiter._max == 7
    assert limiter._window == 30
    assert limiter._fail_open is True  # default: availability over strict limiting


def test_redis_limiter_carries_fail_open_false():
    """Security-sensitive routes (login/register/refresh) pass fail_open=False
    (#234) so an unreachable limiter rejects instead of allowing through."""
    limiter = build_rate_limiter(
        namespace="login",
        max_hits=5,
        window_seconds=60,
        redis_url="redis://localhost:6379/0",
        fail_open=False,
    )
    assert isinstance(limiter, RedisRateLimiter)
    assert limiter._fail_open is False


@pytest.fixture(autouse=True)
def _isolate_registry():
    # http_lifecycle's registry is process-wide module state — isolate it so
    # this file's assertions see only what it registered (#303).
    http_lifecycle._registered.clear()
    yield
    http_lifecycle._registered.clear()


@pytest.mark.asyncio
async def test_redis_limiter_is_registered_for_shutdown_close():
    """#303: build_rate_limiter's Redis-backed limiter is registered with
    http_lifecycle so its connection pool is closed at shutdown — it was
    previously reclaimed only by process exit/GC, like the LLM/STT/pronunciation
    clients were before #280."""
    limiter = build_rate_limiter(
        namespace="login", max_hits=5, window_seconds=60, redis_url="redis://localhost:6379/0"
    )

    assert http_lifecycle._registered == [limiter]

    await http_lifecycle.close_all()  # must not raise, even with no Redis server running
    assert http_lifecycle._registered == []


def test_in_memory_limiter_is_not_registered_for_shutdown_close():
    """No Redis client to close in dev/test mode — nothing should be registered."""
    build_rate_limiter(namespace="login", max_hits=5, window_seconds=60, redis_url="")

    assert http_lifecycle._registered == []
