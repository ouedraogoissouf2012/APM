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


def _turn_lock_key(session_id: int) -> str:
    """Namespaced so a session's turn lock can never collide with a
    client-supplied Idempotency-Key (a UUID) sharing the same (user, key) table."""
    return f"turn-lock:session:{session_id}"


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

    async def acquire_turn_lock(self, user_id: int, session_id: int) -> bool:
        """Claim the single-in-flight-turn lock for a session.

        Returns True iff acquired; False iff a turn is already in flight for this
        session (the caller must then reject the concurrent turn with 409).

        `/turn/stream` carries no per-request idempotency key, so without this two
        concurrent turns for one session (a double-tap, or a retry fired while the
        first is still streaming) read the SAME base transcript and the second's
        persist OVERWRITES the first (a lost turn) while both charge the quota
        (#229). Acquired before the base is read and released when the stream ends,
        so the whole read→persist critical section is serialised. Built on the same
        atomic claim as the idempotency keys, so a stream that crashes without
        releasing self-heals after STALE_CLAIM_SECONDS instead of wedging the
        session forever.
        """
        stale_before = self._now() - timedelta(seconds=STALE_CLAIM_SECONDS)
        return await self._repo.claim(user_id, _turn_lock_key(session_id), stale_before)

    async def release_turn_lock(self, user_id: int, session_id: int) -> None:
        """Release a session's turn lock so the next turn can proceed."""
        await self._repo.release(user_id, _turn_lock_key(session_id))

    @staticmethod
    def _resolve(response: str | None) -> str:
        # A cached response replays verbatim; a still-claimed (None) key means a
        # concurrent request is mid-flight — signal a retry rather than re-run.
        if response is not None:
            return response
        raise ConflictError("This request is already being processed; retry shortly")
