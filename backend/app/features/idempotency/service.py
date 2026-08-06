"""Idempotency for replayable requests (#127, offline-first).

A client that queued a turn while offline may replay it after reconnecting, even
if the server already processed it (the response was lost with the connection).
This service makes that safe: it CLAIMS the key atomically before doing the work,
so two concurrent replays of the same key cannot both process the turn (no
duplicate turn, no double quota charge #119). The first replay runs the work and
caches its result; a later replay returns the cached result; a CONCURRENT replay
that lost the claim gets a 409 (the winner is still processing) and can retry —
by then the result is cached. A failed work releases the claim so it isn't a
poison key that 409s forever.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from app.domain.exceptions import ConflictError
from app.features.idempotency.repository import IdempotencyRepository

# A pending claim older than this is treated as abandoned (its request crashed)
# and may be reclaimed. Must exceed the longest a turn can legitimately take.
STALE_CLAIM_SECONDS = 120


class IdempotencyService:
    def __init__(
        self,
        repo: IdempotencyRepository,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = repo
        self._now = now  # injectable for deterministic tests

    async def run_once(
        self,
        user_id: int,
        key: str | None,
        work: Callable[[], Awaitable[str]],
    ) -> str:
        """Run `work` at most once per (user, key) and return its result.

        With no key, runs the work every time (idempotency is opt-in via the key).
        """
        if not key:
            return await work()

        exists, response = await self._repo.lookup(user_id, key)
        if exists and response is not None:
            return response  # completed earlier: replay the cached result

        # No row, or a pending row (possibly abandoned by a crash). Try to claim
        # or reclaim it — only one concurrent caller wins.
        stale_before = self._now() - timedelta(seconds=STALE_CLAIM_SECONDS)
        if not await self._repo.claim(user_id, key, stale_before):
            # A live claim or a completed result already exists: re-read it.
            _, response = await self._repo.lookup(user_id, key)
            return self._resolve(response)

        # We own the claim: do the work, cache it. On failure, release the claim
        # so the turn can be retried (it was NOT processed to completion).
        try:
            result = await work()
        except Exception:
            await self._repo.release(user_id, key)
            raise
        await self._repo.complete(user_id, key, result)
        return result

    @staticmethod
    def _resolve(response: str | None) -> str:
        # A cached response replays verbatim; a still-claimed (None) key means a
        # concurrent request is mid-flight — signal a retry rather than re-run.
        if response is not None:
            return response
        raise ConflictError("This request is already being processed; retry shortly")
