import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.core.rate_limit import RateLimiter
from app.domain.exceptions import LlmProviderError
from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.conversation.dependencies import (
    get_conversation_rate_limiter,
    get_conversation_turn_service,
)
from app.features.conversation.schemas import TurnIn, TurnOut
from app.features.conversation.turn_service import ConversationTurnService

router = APIRouter(prefix="/sessions/{session_id}", tags=["conversation"])


@router.post("/turn", response_model=TurnOut)
async def take_turn(
    session_id: int,
    payload: TurnIn,
    request: Request,
    current_user: User = Depends(get_current_user),
    limiter: RateLimiter = Depends(get_conversation_rate_limiter),
    service: ConversationTurnService = Depends(get_conversation_turn_service),
) -> TurnOut:
    client_host = request.client.host if request.client else "anonymous"
    await limiter.check(f"turn:{client_host}:user:{current_user.id}")
    result = await service.take_turn(session_id, current_user, payload.text)
    return TurnOut(reply=result.reply)


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
) -> StreamingResponse:
    """Stream the reply as Server-Sent Events: one `chunk` event per sentence
    so the client speaks it immediately, a final `done` event, or an `error`.
    Ownership/quota checks happen before streaming begins."""
    client_host = request.client.host if request.client else "anonymous"
    await limiter.check(f"turn:{client_host}:user:{current_user.id}")

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for sentence in service.stream_turn(
                session_id, current_user, payload.text
            ):
                yield _sse("chunk", {"text": sentence})
            yield _sse("done", {})
        except LlmProviderError:
            yield _sse("error", {"message": "LLM provider failed"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
