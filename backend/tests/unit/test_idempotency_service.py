"""Unit tests for the idempotency service (#127, hardened for #185)."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.exceptions import ConflictError
from app.features.idempotency.service import IdempotencyService


class _InMemoryRepo:
    """Faithful in-memory model of the claim-first repo. A row's response is None
    when CLAIMED-but-pending and a str when COMPLETED. claim() is atomic (no await
    inside) and reclaims a PENDING row older than stale_before, mirroring the SQL
    INSERT ... ON CONFLICT DO UPDATE ... WHERE (response IS NULL AND created_at <)."""

    def __init__(self):
        # (user, key) -> {"response": str|None, "created_at": datetime}
        self._rows: dict[tuple[int, str], dict] = {}

    def seed_pending(self, user_id, key, created_at):
        self._rows[(user_id, key)] = {"response": None, "created_at": created_at}

    async def lookup(self, user_id, key):
        row = self._rows.get((user_id, key))
        if row is None:
            return (False, None)
        return (True, row["response"])

    async def claim(self, user_id, key, stale_before):
        k = (user_id, key)
        row = self._rows.get(k)
        if row is None:
            self._rows[k] = {"response": None, "created_at": datetime.now(UTC)}
            return True
        if row["response"] is None and row["created_at"] < stale_before:
            row["created_at"] = datetime.now(UTC)  # reclaim the abandoned claim
            return True
        return False  # live pending claim, or completed

    async def complete(self, user_id, key, response):
        self._rows[(user_id, key)]["response"] = response

    async def release(self, user_id, key):
        self._rows.pop((user_id, key), None)


def _counting_work(reply="reply"):
    calls = {"n": 0}

    async def work():
        calls["n"] += 1
        return reply

    return work, calls


def _service():
    repo = _InMemoryRepo()
    return IdempotencyService(repo), repo


@pytest.mark.asyncio
async def test_first_call_runs_the_work():
    service, _ = _service()
    work, calls = _counting_work("hello")
    assert await service.run_once(1, "k1", work) == "hello"
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_replay_returns_cached_without_rerunning():
    service, _ = _service()
    work, calls = _counting_work("hello")

    first = await service.run_once(1, "k1", work)
    second = await service.run_once(1, "k1", work)  # replay same key

    assert first == second == "hello"
    assert calls["n"] == 1  # work ran ONCE — no duplicate/double-charge


@pytest.mark.asyncio
async def test_no_key_always_runs():
    service, _ = _service()
    work, calls = _counting_work()
    await service.run_once(1, None, work)
    await service.run_once(1, None, work)
    assert calls["n"] == 2  # idempotency is opt-in via the key


@pytest.mark.asyncio
async def test_keys_are_scoped_per_user():
    service, _ = _service()
    work_a, calls_a = _counting_work("A")
    work_b, calls_b = _counting_work("B")

    a = await service.run_once(1, "same", work_a)
    b = await service.run_once(2, "same", work_b)  # different user, same key text

    assert a == "A"
    assert b == "B"
    assert calls_a["n"] == 1 and calls_b["n"] == 1


@pytest.mark.asyncio
async def test_concurrent_same_key_processes_the_work_exactly_once():
    # THE regression #185 was about: two overlapping replays of the same key must
    # NOT both run the work. The second (which lost the claim) gets a 409 while the
    # winner is still processing, and can retry later for the cached result.
    service, _ = _service()
    started = asyncio.Event()
    finish = asyncio.Event()
    calls = {"n": 0}

    async def slow_work():
        calls["n"] += 1
        started.set()
        await finish.wait()  # hold so a concurrent call interleaves mid-work
        return "reply"

    winner = asyncio.create_task(service.run_once(1, "k", slow_work))
    await started.wait()  # the first call has claimed and is inside work()

    # A concurrent replay of the same key sees the pending claim -> 409, no re-run.
    with pytest.raises(ConflictError):
        await service.run_once(1, "k", slow_work)

    finish.set()
    assert await winner == "reply"
    assert calls["n"] == 1  # processed exactly once despite the concurrent replay


@pytest.mark.asyncio
async def test_a_retry_after_the_winner_finishes_returns_the_cached_result():
    service, _ = _service()
    work, calls = _counting_work("done")

    await service.run_once(1, "k", work)  # winner completes
    # A later replay (the earlier concurrent loser retrying) now gets the cache.
    assert await service.run_once(1, "k", work) == "done"
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_failed_work_releases_the_claim_so_a_retry_can_succeed():
    # A failed work() must NOT poison the key (it was not processed to completion).
    service, _ = _service()

    async def boom():
        raise RuntimeError("network down mid-turn")

    with pytest.raises(RuntimeError):
        await service.run_once(1, "k", boom)

    # The claim was released: a retry re-claims and succeeds (no permanent 409).
    async def ok():
        return "recovered"

    assert await service.run_once(1, "k", ok) == "recovered"


@pytest.mark.asyncio
async def test_a_stale_pending_claim_is_reclaimed_not_stuck_forever():
    # If a request CRASHES between claiming and completing, the pending claim must
    # not 409 forever — after STALE_CLAIM_SECONDS a replay reclaims and processes.
    service, repo = _service()
    repo.seed_pending(1, "k", created_at=datetime.now(UTC) - timedelta(minutes=10))

    work, calls = _counting_work("recovered")
    assert await service.run_once(1, "k", work) == "recovered"
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_a_fresh_pending_claim_is_not_reclaimed():
    # A claim that is still fresh (a live concurrent request) must NOT be stolen.
    service, repo = _service()
    repo.seed_pending(1, "k", created_at=datetime.now(UTC))

    work, calls = _counting_work()
    with pytest.raises(ConflictError):
        await service.run_once(1, "k", work)
    assert calls["n"] == 0  # did not steal the live claim
