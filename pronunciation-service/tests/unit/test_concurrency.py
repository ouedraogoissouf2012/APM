"""Unit tests for InferenceGate (TDD, written first).

The gate is what keeps the CPU-bound wav2vec2 inference from (a) blocking the
asyncio event loop and (b) over-subscribing the CPU when several requests arrive
at once. It must:
- run the blocking function OFF the event loop (in a worker thread), and
- admit at most `max_concurrent` inferences at a time, queueing the rest.
"""

import asyncio
import threading
import time

import pytest

from pronunciation.core.concurrency import InferenceGate


@pytest.mark.asyncio
async def test_runs_the_function_off_the_event_loop():
    # The gate must execute blocking work in a worker thread, NOT the loop's thread.
    loop_thread = threading.current_thread().ident
    gate = InferenceGate(max_concurrent=1)

    def where_am_i() -> int:
        return threading.current_thread().ident

    worker_thread = await gate.run(where_am_i)
    assert worker_thread != loop_thread  # ran off the event loop


@pytest.mark.asyncio
async def test_returns_the_functions_result():
    gate = InferenceGate(max_concurrent=1)
    assert await gate.run(lambda: 21 * 2) == 42


@pytest.mark.asyncio
async def test_serializes_when_max_concurrent_is_one():
    # With a limit of 1, overlapping calls must NOT run concurrently: at no point
    # may two functions be inside their critical section together.
    gate = InferenceGate(max_concurrent=1)
    active = 0
    max_seen = 0
    lock = threading.Lock()

    def work() -> None:
        nonlocal active, max_seen
        with lock:
            active += 1
            max_seen = max(max_seen, active)
        time.sleep(0.05)
        with lock:
            active -= 1

    await asyncio.gather(*(gate.run(work) for _ in range(5)))
    assert max_seen == 1  # never more than one inference at a time


@pytest.mark.asyncio
async def test_allows_configured_parallelism():
    # With a higher limit, up to that many may overlap (proves it's not always 1).
    gate = InferenceGate(max_concurrent=3)
    active = 0
    max_seen = 0
    lock = threading.Lock()

    def work() -> None:
        nonlocal active, max_seen
        with lock:
            active += 1
            max_seen = max(max_seen, active)
        time.sleep(0.05)
        with lock:
            active -= 1

    await asyncio.gather(*(gate.run(work) for _ in range(6)))
    assert 2 <= max_seen <= 3  # genuine parallelism, capped at the limit


@pytest.mark.asyncio
async def test_propagates_exceptions():
    gate = InferenceGate(max_concurrent=1)

    def boom() -> None:
        raise ValueError("inference failed")

    with pytest.raises(ValueError, match="inference failed"):
        await gate.run(boom)


@pytest.mark.asyncio
async def test_semaphore_released_after_exception():
    # A failing call must still release its slot, or the gate would deadlock.
    gate = InferenceGate(max_concurrent=1)

    def boom() -> None:
        raise ValueError("x")

    for _ in range(3):
        with pytest.raises(ValueError):
            await gate.run(boom)
    # If the slot leaked, this final call would hang; it must complete.
    assert await gate.run(lambda: "ok") == "ok"
