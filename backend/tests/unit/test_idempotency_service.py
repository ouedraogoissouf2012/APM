"""Unit tests for the idempotency service (#127)."""

import pytest

from app.features.idempotency.service import IdempotencyService


class _InMemoryRepo:
    def __init__(self):
        self._store: dict[tuple[int, str], str] = {}

    async def get_response(self, user_id, key):
        return self._store.get((user_id, key))

    async def remember(self, user_id, key, response):
        self._store[(user_id, key)] = response


def _counting_work(reply="reply"):
    calls = {"n": 0}

    async def work():
        calls["n"] += 1
        return reply

    return work, calls


@pytest.mark.asyncio
async def test_first_call_runs_the_work():
    work, calls = _counting_work("hello")
    result = await IdempotencyService(_InMemoryRepo()).run_once(1, "k1", work)
    assert result == "hello"
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_replay_returns_cached_without_rerunning():
    repo = _InMemoryRepo()
    service = IdempotencyService(repo)
    work, calls = _counting_work("hello")

    first = await service.run_once(1, "k1", work)
    second = await service.run_once(1, "k1", work)  # replay same key

    assert first == second == "hello"
    assert calls["n"] == 1  # work ran ONCE — no duplicate/double-charge


@pytest.mark.asyncio
async def test_no_key_always_runs():
    service = IdempotencyService(_InMemoryRepo())
    work, calls = _counting_work()
    await service.run_once(1, None, work)
    await service.run_once(1, None, work)
    assert calls["n"] == 2  # idempotency is opt-in via the key


@pytest.mark.asyncio
async def test_keys_are_scoped_per_user():
    repo = _InMemoryRepo()
    service = IdempotencyService(repo)
    work_a, calls_a = _counting_work("A")
    work_b, calls_b = _counting_work("B")

    a = await service.run_once(1, "same", work_a)
    b = await service.run_once(2, "same", work_b)  # different user, same key text

    assert a == "A"
    assert b == "B"  # not cross-contaminated
    assert calls_a["n"] == 1 and calls_b["n"] == 1
