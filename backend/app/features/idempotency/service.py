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
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum

from app.domain.exceptions import ConflictError
from app.features.idempotency.repository import IdempotencyRepository

# A pending claim older than this is treated as abandoned (its request crashed)
# and may be reclaimed. Must exceed the longest a turn can legitimately take.
STALE_CLAIM_SECONDS = 120


def _turn_lock_key(session_id: int) -> str:
    """Namespaced so a session's turn lock can never collide with a
    client-supplied Idempotency-Key (a UUID) sharing the same (user, key) table."""
    return f"turn-lock:session:{session_id}"


class ClaimStatus(Enum):
    """Outcome of claiming an idempotency key for a STREAMING operation, which
    drives the work itself (unlike run_once, which runs the work inline)."""

    CLAIMED = "claimed"  # this caller owns it — do the work, then complete()/release()
    COMPLETED = "completed"  # already processed — replay the cached response, don't re-run
    IN_FLIGHT = "in_flight"  # a concurrent caller holds the claim — signal a retry (409)


@dataclass(frozen=True)
class ClaimOutcome:
    status: ClaimStatus
    response: str | None = None  # the cached reply, set only when COMPLETED


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

        outcome = await self.begin(user_id, key)
        if outcome.status is ClaimStatus.COMPLETED:
            assert outcome.response is not None  # COMPLETED always carries the cached reply
            return outcome.response
        if outcome.status is ClaimStatus.IN_FLIGHT:
            raise ConflictError("This request is already being processed; retry shortly")

        # We own the claim: do the work, cache it. On failure, release the claim
        # so the turn can be retried (it was NOT processed to completion).
        try:
            result = await work()
        except Exception:
            await self.release(user_id, key)
            raise
        await self.complete(user_id, key, result)
        return result

    async def begin(self, user_id: int, key: str) -> ClaimOutcome:
        """Resolve an idempotency claim WITHOUT running the work — for a streaming
        caller that drives the work itself and must finalise with complete()/release().

        - COMPLETED: this key was already processed; replay `outcome.response`.
        - IN_FLIGHT: a concurrent caller holds the claim; tell the client to retry (409).
        - CLAIMED: this caller now owns the claim; do the work, then complete()/release().
        """
        exists, response = await self._repo.lookup(user_id, key)
        if exists and response is not None:
            return ClaimOutcome(ClaimStatus.COMPLETED, response)

        # No row, or a pending row (possibly abandoned by a crash). Try to claim
        # or reclaim it — the unique (user, key) constraint lets only one caller win.
        stale_before = self._now() - timedelta(seconds=STALE_CLAIM_SECONDS)
        if not await self._repo.claim(user_id, key, stale_before):
            # A live claim or a completed result already exists: re-read to tell apart.
            _, response = await self._repo.lookup(user_id, key)
            if response is not None:
                return ClaimOutcome(ClaimStatus.COMPLETED, response)
            return ClaimOutcome(ClaimStatus.IN_FLIGHT)
        return ClaimOutcome(ClaimStatus.CLAIMED)

    async def complete(self, user_id: int, key: str, response: str) -> None:
        """Cache the result of an owned claim so a later replay returns it verbatim."""
        await self._repo.complete(user_id, key, response)

    async def release(self, user_id: int, key: str) -> None:
        """Drop an owned claim whose work did NOT complete, so a retry can re-claim
        it (no poison key that 409s forever)."""
        await self._repo.release(user_id, key)

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
