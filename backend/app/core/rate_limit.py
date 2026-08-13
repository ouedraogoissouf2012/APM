"""Rate limiting as a swappable abstraction.

`RateLimiter` is the interface the API depends on. `InMemoryRateLimiter` is a
sliding-window implementation for a single process; `RedisRateLimiter` shares
limits across every worker/instance via Redis (OCP/DIP/LSP). `NoOpRateLimiter`
disables limiting (used as the default in tests).
"""

import logging
import time
from collections import defaultdict, deque
from typing import Any, Protocol

from redis.exceptions import RedisError

from app.domain.exceptions import RateLimitedError

_logger = logging.getLogger(__name__)


class RateLimiter(Protocol):
    async def check(self, key: str) -> None:
        """Raise RateLimitedError if `key` has exceeded its allowance."""
        ...


def user_rate_limit_key(namespace: str, user_id: int) -> str:
    """Build a per-user rate-limit key with NO IP component (#356).

    An IP-keyed bucket lets an account rotate its apparent IP (VPN, or
    X-Forwarded-For under trust_proxy_headers) to reset a per-user quota on a
    paid provider — a denial-of-wallet. Every authenticated, paid-provider
    endpoint keys its limiter through this one function instead of a
    hand-rolled f-string, so that invariant lives in a single place rather
    than being copy-pasted (and potentially re-broken) at each call site.
    """
    return f"{namespace}:user:{user_id}"


class InMemoryRateLimiter:
    """Fixed-window in-memory limiter (dev/test only, not for production).

    Single-process only — each worker has its own limiter, so limits are per-worker
    (limit × N workers). Evicts expired buckets and enforces a global entry cap
    to prevent a DoS via high-cardinality keys (attacker-controlled emails/tokens).

    Production should use RedisRateLimiter instead."""

    def __init__(self, max_hits: int, window_seconds: int, *, max_keys: int = 1000) -> None:
        self._max = max_hits
        self._window = window_seconds
        self._max_keys = max_keys
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def check(self, key: str) -> None:
        now = time.monotonic()
        # Evict expired hits from this key's sliding window (normal operation).
        if key in self._hits:
            bucket = self._hits[key]
            while bucket and now - bucket[0] > self._window:
                bucket.popleft()
            # Cleanup: if bucket is now empty, remove the key entirely.
            if not bucket:
                del self._hits[key]
        # If this is a new key and we're at capacity, evict the oldest bucket
        # before accepting it (FIFO eviction when at capacity).
        if key not in self._hits and len(self._hits) >= self._max_keys:
            oldest_key = next(iter(self._hits))  # First key inserted (FIFO order)
            del self._hits[oldest_key]
        # Now get or create the bucket for this key.
        bucket = self._hits[key]
        # Check rate limit: if bucket is at capacity, reject.
        if len(bucket) >= self._max:
            raise RateLimitedError("Too many attempts, please retry later")
        # Accept the hit.
        bucket.append(now)


# Atomically increments the window's hit counter and, on the FIRST hit in this
# window, sets its expiry — one Lua execution server-side (Redis runs scripts
# single-threaded, so nothing can interleave). Doing this as two separate calls
# (INCR then EXPIRE) leaves a gap where a crashed worker or a dropped connection
# between them orphans a key with no TTL: it never expires, leaking Redis memory
# forever under sustained multi-worker traffic — the exact unbounded-growth
# failure #234 set out to fix, just moved from the in-process dict to Redis.
_INCR_AND_EXPIRE_SCRIPT = """
local count = redis.call("INCR", KEYS[1])
if count == 1 then
    redis.call("EXPIRE", KEYS[1], ARGV[1])
end
return count
"""


class RedisScript(Protocol):
    """What `Redis.register_script()` returns: a callable that runs the script
    via EVALSHA, transparently loading it (EVAL, which also caches it
    server-side) the first time or after a cache flush. Depending on this
    instead of a raw client keeps `RedisRateLimiter` from re-sending the full
    script body on every check() — only a hash goes over the wire once warm."""

    async def __call__(
        self, keys: list[str] | None = None, args: list[str] | None = None
    ) -> int: ...


class RedisRateLimiter:
    """Fixed-window limiter shared across every worker/instance via Redis.

    Depends on a pre-registered `RedisScript` (DIP), not a raw client: script
    registration is the factory's concern, this class only runs it.
    """

    # A sustained outage must not flood logs with one warning per request —
    # log the failure at most once per this many seconds.
    _FAILURE_LOG_THROTTLE_SECONDS = 30.0

    def __init__(
        self,
        script: RedisScript,
        *,
        namespace: str,
        max_hits: int,
        window_seconds: int,
        fail_open: bool = True,
        client: Any | None = None,
    ) -> None:
        self._script = script
        self._namespace = namespace
        self._max = max_hits
        self._window = window_seconds
        self._fail_open = fail_open
        self._last_failure_log = 0.0
        # Only the factory (build_rate_limiter) passes a client — it's the one
        # closed at shutdown (#303). Optional so tests can construct a limiter
        # from a bare script fake without a Redis client to close.
        self._client = client

    async def check(self, key: str) -> None:
        bucket = int(time.time() // self._window)
        redis_key = f"rate:{self._namespace}:{bucket}:{key}"
        try:
            hits = await self._script(keys=[redis_key], args=[str(self._window + 1)])
        except RedisError:
            self._log_failure_throttled()
            if self._fail_open:
                # A Redis outage must not take down every rate-limited route
                # (#234 multi-worker): allow the request, losing the abuse
                # guard only for the outage's duration. The right default for
                # routes where over-allowing is the lesser risk — billing/quota
                # enforcement lives elsewhere (session turn metering), so
                # nothing authoritative depends on this.
                return
            # Security-sensitive routes (login/register/refresh) opt into
            # fail_open=False instead: an unreachable limiter must not hand
            # out unlimited credential-stuffing attempts during an outage.
            # Raised as RateLimitedError (not a bespoke error) so callers need
            # no extra handling — "can't verify the limit" is treated exactly
            # like "limit exceeded".
            raise RateLimitedError("Rate limiter unavailable, try again later") from None
        if hits > self._max:
            raise RateLimitedError("Too many attempts, please retry later")

    def _log_failure_throttled(self) -> None:
        now = time.monotonic()
        if now - self._last_failure_log < self._FAILURE_LOG_THROTTLE_SECONDS:
            return
        self._last_failure_log = now
        _logger.warning(
            "Redis rate limiter unavailable (namespace=%s, fail_open=%s)",
            self._namespace,
            self._fail_open,
            exc_info=True,
        )

    async def aclose(self) -> None:
        """Close the underlying Redis client's connection pool at process
        shutdown (app.core.http_lifecycle, #303). A no-op when constructed
        without a client (e.g. tests that only exercise the script)."""
        if self._client is not None:
            await self._client.aclose()


class NoOpRateLimiter:
    async def check(self, key: str) -> None:
        return None
