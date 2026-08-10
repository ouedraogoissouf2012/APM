import json
import logging
from collections.abc import AsyncIterator
from dataclasses import asdict

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse

from app.api.client_ip import client_ip
from app.config import get_settings
from app.core.rate_limit import RateLimiter
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
from app.features.idempotency.dependencies import get_idempotency_service
from app.features.idempotency.service import IdempotencyService

router = APIRouter(prefix="/sessions/{session_id}", tags=["conversation"])


@router.post("/turn", response_model=TurnOut)
async def take_turn(
    session_id: int,
    payload: TurnIn,
    request: Request,
    current_user: User = Depends(get_current_user),
    limiter: RateLimiter = Depends(get_conversation_rate_limiter),
    service: ConversationTurnService = Depends(get_conversation_turn_service),
    idempotency: IdempotencyService = Depends(get_idempotency_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> TurnOut:
    """Non-streaming turn (used for offline replay, #127). An optional
    `Idempotency-Key` header makes a replay safe: the same key returns the same
    reply without re-processing the turn or re-charging the quota (#119)."""
    client_host = client_ip(request, get_settings().trust_proxy_headers)
    await limiter.check(f"turn:{client_host}:user:{current_user.id}")

    async def _process() -> str:
        result = await service.take_turn(session_id, current_user, payload.text)
        return result.reply

    reply = await idempotency.run_once(current_user.id, idempotency_key, _process)
    return TurnOut(reply=reply)


def _sse(event: str, data: dict) -> str:
    """Format one Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/turn/stream")
async def stream_turn(
    session_id: int,
    payload: TurnIn,
    request: Request,
    current_user: User = Depends(get_current_user),
    limiter: RateLimiter = Depends(get_conversation_rate_limiter),
    service: ConversationTurnService = Depends(get_conversation_turn_service),
    idempotency: IdempotencyService = Depends(get_idempotency_service),
) -> StreamingResponse:
    """Stream the reply as Server-Sent Events: one `chunk` event per sentence
    so the client speaks it immediately, then at most one `correction` event
    (the learner's mistake + fix + rule + alternatives), a final `done`, or an
    `error`. Ownership and session state are validated eagerly (proper 404/409)
    before the stream is committed."""
    client_host = client_ip(request, get_settings().trust_proxy_headers)
    await limiter.check(f"turn:{client_host}:user:{current_user.id}")

    # One in-flight turn per session (#229). Unlike /turn this endpoint has no
    # Idempotency-Key, so two concurrent turns (double-tap, or a retry fired while
    # the first is still streaming) would read the same base transcript and the
    # second's persist would OVERWRITE the first + double-charge the quota. Acquire
    # BEFORE prepare_turn reads the base so the whole read→persist section is
    # serialised; a concurrent turn is refused with 409. Released when the stream
    # ends (or auto-reclaimed after ~120s if the request crashes mid-stream).
    if not await idempotency.acquire_turn_lock(current_user.id, session_id):
        raise ConflictError("A turn is already in progress for this session")
    prepared = None
    try:
        prepared = await service.prepare_turn(session_id, current_user, payload.text)
    finally:
        if prepared is None:
            # prepare failed (not owned / ended / cancelled) before any streaming —
            # free the lock so the session isn't wedged until the stale window.
            await idempotency.release_turn_lock(current_user.id, session_id)

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in service.stream_prepared(prepared):
                if isinstance(event, ReplyChunk):
                    yield _sse("chunk", {"text": event.text})
                elif isinstance(event, AudioChunk):
                    yield _sse("audio", {"audio": event.audio_b64, "mime": event.mime})
                elif isinstance(event, CorrectionReady):
                    yield _sse("correction", asdict(event.correction))
            yield _sse("done", {})
        except LlmProviderError:
            yield _sse("error", {"message": "LLM provider failed"})
        except Exception:
            # Any other failure (TTS, DB, unexpected) must still close the stream
            # with a typed error event — never a silently broken frame that leaves
            # the client hanging (#123). Logged for diagnosis.
            logging.getLogger(__name__).exception("Unexpected error during turn stream")
            yield _sse("error", {"message": "Turn failed"})
        finally:
            # Runs on normal completion, on error, AND on client disconnect
            # (GeneratorExit) — so the session's turn lock is always freed.
            await idempotency.release_turn_lock(current_user.id, session_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
