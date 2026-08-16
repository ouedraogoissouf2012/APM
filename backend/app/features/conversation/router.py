import json
import logging
from collections.abc import AsyncIterator
from dataclasses import asdict

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse

from app.core.rate_limit import RateLimiter, user_rate_limit_key
from app.domain.exceptions import ConflictError, LlmProviderError
from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.conversation.dependencies import (
    get_conversation_rate_limiter,
    get_conversation_turn_service,
)
from app.features.conversation.schemas import TurnIn, TurnOut
from app.features.conversation.turn_service import (
    AudioChunk,
    ConversationTurnService,
    CorrectionReady,
    ReplyChunk,
)
from app.features.idempotency.dependencies import (
    FreshIdempotencyFactory,
    get_fresh_idempotency_factory,
    get_idempotency_service,
)
from app.features.idempotency.service import ClaimStatus, IdempotencyService

router = APIRouter(prefix="/sessions/{session_id}", tags=["conversation"])

_TURN_LOCK_CONFLICT_MESSAGE = "A turn is already in progress for this session"


@router.post("/turn", response_model=TurnOut)
async def take_turn(
    session_id: int,
    payload: TurnIn,
    current_user: User = Depends(get_current_user),
    limiter: RateLimiter = Depends(get_conversation_rate_limiter),
    service: ConversationTurnService = Depends(get_conversation_turn_service),
    idempotency: IdempotencyService = Depends(get_idempotency_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> TurnOut:
    """Non-streaming turn (used for offline replay, #127). An optional
    `Idempotency-Key` header makes a replay safe: the same key returns the same
    reply without re-processing the turn or re-charging the quota (#119).

    Serialised by the SAME per-session turn lock as /turn/stream (#256, #299):
    without it, two CONCURRENT turns with no Idempotency-Key would read the
    same base transcript and the second's persist would overwrite the first
    (a lost turn) while both charge the quota. Acquired before take_turn reads
    the base transcript, released once it returns (success or failure) — the
    lock section is scoped to `_process`, so run_once's existing
    except-Exception-then-release already frees a newly-claimed idempotency
    key when the lock is contended, with no duplicated cleanup here."""
    # Keyed by user_id, not IP (#384): /turn is the paid endpoint's single
    # heaviest call (LLM completion + per-sentence TTS) — an IP-keyed bucket
    # would let a rotated apparent IP (or, per #383, a spoofed
    # X-Forwarded-For) reset it, defeating the limiter entirely for an
    # inf-quota (premium) account. Same helper every other paid endpoint uses.
    await limiter.check(user_rate_limit_key("turn", current_user.id))

    async def _process() -> str:
        if not await idempotency.acquire_turn_lock(current_user.id, session_id):
            raise ConflictError(_TURN_LOCK_CONFLICT_MESSAGE)
        try:
            result = await service.take_turn(
                session_id, current_user, payload.text, practiced_at=payload.practiced_at
            )
            return result.reply
        finally:
            try:
                await idempotency.release_turn_lock(current_user.id, session_id)
            except Exception:
                # Best-effort, like the meter and on_persisted's idempotency.complete
                # below: a release failure must never mask take_turn's real outcome —
                # neither a successful, already-persisted+metered reply nor a genuine
                # domain error (404/409) should be replaced by this cleanup call's own
                # failure (Python's finally-overrides-return/raise semantics would do
                # exactly that otherwise). Worst case the lock self-heals via the
                # stale-reclaim window (~STALE_CLAIM_SECONDS) instead of a transient
                # DB blip here corrupting the response or re-opening #299's race via a
                # wrongly-released idempotency claim.
                logging.getLogger(__name__).warning(
                    "Turn lock release failed for session %s", session_id, exc_info=True
                )

    reply = await idempotency.run_once(current_user.id, idempotency_key, _process)
    return TurnOut(reply=reply)


def _sse(event: str, data: dict) -> str:
    """Format one Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


async def _replay_completed(reply: str) -> AsyncIterator[str]:
    """Re-emit an already-processed turn's reply as a stream WITHOUT re-running the
    LLM, re-persisting the transcript, or re-charging the quota (#261). The reply is
    replayed as a single chunk — the per-sentence split, audio and correction were
    delivered on the first, successful pass and are not cached."""
    yield _sse("chunk", {"text": reply})
    yield _sse("done", {})


@router.post("/turn/stream")
async def stream_turn(
    session_id: int,
    payload: TurnIn,
    current_user: User = Depends(get_current_user),
    limiter: RateLimiter = Depends(get_conversation_rate_limiter),
    service: ConversationTurnService = Depends(get_conversation_turn_service),
    idempotency: IdempotencyService = Depends(get_idempotency_service),
    fresh_idempotency: FreshIdempotencyFactory = Depends(get_fresh_idempotency_factory),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> StreamingResponse:
    """Stream the reply as Server-Sent Events: one `chunk` event per sentence
    so the client speaks it immediately, then at most one `correction` event
    (the learner's mistake + fix + rule + alternatives), a final `done`, or an
    `error`. Ownership and session state are validated eagerly (proper 404/409)
    before the stream is committed.

    Two layers stop a double-tour from corrupting the transcript or double-charging
    the quota: a per-session turn lock serialises CONCURRENT turns (#256), and an
    optional `Idempotency-Key` header dedupes a SEQUENTIAL retry (#261) — the same
    key replays its cached reply without re-processing, a still-in-flight key 409s."""
    # Keyed by user_id, not IP (#384) — see take_turn's identical comment above.
    await limiter.check(user_rate_limit_key("turn", current_user.id))

    # Idempotency-Key layer (#261): dedupe a REPLAYED turn (network retry / offline
    # replay). A completed key replays its cached reply with no processing and no
    # lock; a still-in-flight key 409s. The per-session lock below can't do this —
    # it only stops concurrency, it can't tell a deliberate repeat from a retry.
    newly_claimed = False
    if idempotency_key:
        outcome = await idempotency.begin(current_user.id, idempotency_key)
        if outcome.status is ClaimStatus.IN_FLIGHT:
            raise ConflictError("This request is already being processed; retry shortly")
        if outcome.status is ClaimStatus.COMPLETED:
            return StreamingResponse(
                _replay_completed(outcome.response or ""),
                media_type="text/event-stream",
                headers=_SSE_HEADERS,
            )
        newly_claimed = True  # we own the key — release it if anything below fails

    # One in-flight turn per session (#256): two CONCURRENT turns (double-tap, or a
    # retry fired while the first is still streaming) would read the same base
    # transcript and the second's persist would OVERWRITE the first + double-charge.
    # Acquire BEFORE prepare_turn reads the base so the whole read→persist section is
    # serialised; a concurrent turn is refused with 409. Released when the stream ends
    # (or auto-reclaimed after ~120s if the request crashes mid-stream).
    if not await idempotency.acquire_turn_lock(current_user.id, session_id):
        if newly_claimed and idempotency_key is not None:
            await idempotency.release(current_user.id, idempotency_key)
        raise ConflictError(_TURN_LOCK_CONFLICT_MESSAGE)
    prepared = None
    try:
        prepared = await service.prepare_turn(session_id, current_user, payload.text)
    finally:
        if prepared is None:
            # prepare failed (not owned / ended / cancelled) before any streaming —
            # free the lock so the session isn't wedged until the stale window, and
            # release a fresh key so a 404/409 doesn't poison it into a phantom 409.
            await idempotency.release_turn_lock(current_user.id, session_id)
            if newly_claimed and idempotency_key is not None:
                await idempotency.release(current_user.id, idempotency_key)

    # `completed` flips to True the instant the turn is persisted + metered AND its
    # key is cached — inside on_persisted, which stream_prepared awaits right after
    # the persist, BEFORE any correction/done frame. So a client disconnect on a later
    # frame can no longer leave the side effect committed yet the key un-completed
    # (which a retry would re-persist and double-charge). It also gates the release
    # below: on failure we only free a claim whose work never took effect (#261).
    completed = False

    async def on_persisted(reply: str) -> None:
        nonlocal completed
        completed = True  # side effects are committed — never release this key now
        if idempotency_key:
            try:
                # A POST-I/O write: the request connection was handed back at the
                # LLM boundary (#399), so this runs on a FRESH short-lived session,
                # not the detached request one.
                async with fresh_idempotency() as idem:
                    await idem.complete(current_user.id, idempotency_key, reply)
            except Exception:
                # Best-effort, like the meter: a failed cache leaves the key to the
                # stale-reclaim path rather than turning a good turn into an error.
                logging.getLogger(__name__).warning(
                    "Idempotency completion failed for a streamed turn", exc_info=True
                )

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in service.stream_prepared(prepared, on_persisted):
                if isinstance(event, ReplyChunk):
                    yield _sse("chunk", {"text": event.text})
                elif isinstance(event, AudioChunk):
                    yield _sse("audio", {"audio": event.audio_b64, "mime": event.mime})
                elif isinstance(event, CorrectionReady):
                    yield _sse("correction", asdict(event.correction))
            yield _sse("done", {})
        except LlmProviderError:
            if idempotency_key and not completed:
                async with fresh_idempotency() as idem:
                    await idem.release(current_user.id, idempotency_key)
            yield _sse("error", {"message": "LLM provider failed"})
        except Exception:
            # Any other failure (TTS, DB, unexpected) must still close the stream
            # with a typed error event — never a silently broken frame that leaves
            # the client hanging (#123). Logged for diagnosis.
            logging.getLogger(__name__).exception("Unexpected error during turn stream")
            if idempotency_key and not completed:
                async with fresh_idempotency() as idem:
                    await idem.release(current_user.id, idempotency_key)
            yield _sse("error", {"message": "Turn failed"})
        finally:
            # Runs on normal completion, on error, AND on client disconnect
            # (GeneratorExit) — so the session's turn lock is always freed. On a
            # FRESH session (#399): the request connection was released at the LLM
            # boundary, so reusing the request session from inside this streaming
            # task group would raise MissingGreenlet.
            async with fresh_idempotency() as idem:
                await idem.release_turn_lock(current_user.id, session_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
