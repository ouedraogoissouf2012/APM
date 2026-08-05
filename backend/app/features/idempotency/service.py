"""Idempotency for replayable requests (#127, offline-first).

A client that queued a turn while offline may replay it after reconnecting, even
if the server already processed it (the response was lost with the connection).
This service makes that safe: the first call with a key runs the work and stores
its result; any replay with the same key returns the stored result WITHOUT
re-running the work — so a turn is never duplicated and the quota (#119) is never
charged twice.
"""

from collections.abc import Awaitable, Callable

from app.features.idempotency.repository import IdempotencyRepository


class IdempotencyService:
    def __init__(self, repo: IdempotencyRepository) -> None:
        self._repo = repo

    async def run_once(
        self,
        user_id: int,
        key: str | None,
        work: Callable[[], Awaitable[str]],
    ) -> str:
        """Run `work` at most once per (user, key) and return its result.

        With no key, behaves normally (runs the work every time) — idempotency is
        opt-in via the client-supplied key. With a key, a replay returns the
        stored result and never re-runs the work.
        """
        if not key:
            return await work()

        cached = await self._repo.get_response(user_id, key)
        if cached is not None:
            return cached

        result = await work()
        await self._repo.remember(user_id, key, result)
        return result
