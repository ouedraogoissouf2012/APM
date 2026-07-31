"""Bounded, off-loop execution for the CPU-bound acoustic inference.

Two problems this solves, both measured on the real service:

1. wav2vec2 inference is a synchronous, CPU-bound call that takes seconds. Running
   it directly in an `async def` endpoint blocks asyncio's event loop, so the
   server can't even answer a health check while one score is computing.
   -> we run it in a worker thread (`run_in_threadpool`), keeping the loop free.

2. Each torch inference wants several CPU threads. Letting many run at once
   over-subscribes the cores (N requests x threads-per-inference > cores), which
   thrashes and blows latency up (observed ~35 s under load vs ~4 s alone).
   -> a semaphore admits at most `max_concurrent` inferences; the rest queue.

`max_concurrent` is configuration, not a magic number: 1 is the right default for
a single CPU instance, but a multi-core / GPU deployment can raise it.
"""

import asyncio
from collections.abc import Callable
from typing import TypeVar

from starlette.concurrency import run_in_threadpool

_T = TypeVar("_T")


class InferenceGate:
    """Serialises and off-loads blocking inference calls."""

    def __init__(self, max_concurrent: int = 1) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self.max_concurrent = max_concurrent

    async def run(self, fn: Callable[..., _T], *args: object, **kwargs: object) -> _T:
        """Run blocking `fn` in a worker thread, admitting at most `max_concurrent`
        at once. The semaphore is always released, even if `fn` raises."""
        async with self._semaphore:
            return await run_in_threadpool(fn, *args, **kwargs)
