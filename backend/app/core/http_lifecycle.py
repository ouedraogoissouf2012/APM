"""Process-wide shutdown for the cached HTTP clients (#280).

The provider factories keep ONE HTTP client — one connection pool — per
configuration for the whole process lifetime (`lru_cache`): the LLM
(`AsyncOpenAI`), STT (`AsyncOpenAI`) and pronunciation (`httpx.AsyncClient`)
clients. Nothing closed those pools at shutdown, so they were reclaimed only by
process exit / GC — noisy `ResourceWarning`s in tests, and, in the
dynamic-reconfiguration scenario #280 describes (more than `maxsize` distinct
configs), an `lru_cache` eviction drops a provider whose client then never gets
closed at all.

Every client-owning provider registers itself here at build time and exposes
`aclose()`; `close_all()` closes them once, from the app lifespan's shutdown.
That gives an explicit, best-effort teardown and bounds any eviction leak to the
process lifetime instead of forever.
"""

import logging
from typing import Protocol

_logger = logging.getLogger(__name__)


class AsyncCloseable(Protocol):
    async def aclose(self) -> None: ...


# Module-level because the caches it mirrors are themselves module-level, process
# wide singletons. Mutated only during first-use (append) and shutdown (drain) on
# the single event loop, so no locking is needed.
_registered: list[AsyncCloseable] = []


def register_closeable[T: AsyncCloseable](provider: T) -> T:
    """Record a client-owning provider so its connection pool is closed at
    shutdown. Returns the provider unchanged so a factory can wrap construction
    inline: ``return register_closeable(HttpGopProvider(...))``."""
    _registered.append(provider)
    return provider


async def close_all() -> None:
    """Close every registered provider's HTTP client, once, best-effort. A
    failure to close one must not stop the others (nor abort shutdown), so each
    is closed under its own guard and the registry is always drained."""
    while _registered:
        provider = _registered.pop()
        try:
            await provider.aclose()
        except Exception:
            _logger.warning(
                "Failed to close %s HTTP client at shutdown",
                type(provider).__name__,
                exc_info=True,
            )
