import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.rate_limit import RateLimiter, user_rate_limit_key
from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.voice_data.dependencies import (
    get_voice_data_export_rate_limiter,
    get_voice_data_repository,
    get_voice_data_service,
)
from app.features.voice_data.repository import VoiceDataStreamSource
from app.features.voice_data.schemas import VoiceDataEraseOut, VoiceDataExportOut
from app.features.voice_data.service import VoiceDataService

router = APIRouter(prefix="/me/voice-data", tags=["voice-data"])


async def _stream_export_json(source: VoiceDataStreamSource, user_id: int) -> AsyncIterator[bytes]:
    """Assemble the SAME JSON document `VoiceDataExportOut` describes, one
    category/row at a time off a server-side cursor (#365) — never holding the
    learner's full voice-derived history as one Python list. The bytes sent
    over the wire are byte-for-byte a normal JSON body: chunked transfer
    encoding is transparent to any HTTP client (incl. the mobile app's
    plain `jsonDecode` on the received body), so this is not a contract change.
    """
    yield b'{"raw_audio_retained": false'
    categories: tuple[tuple[str, AsyncIterator[dict]], ...] = (
        ("utterances", source.stream_utterances(user_id)),
        ("vocabulary", source.stream_vocabulary(user_id)),
        ("debriefs", source.stream_debriefs(user_id)),
        ("review_items", source.stream_review_items(user_id)),
    )
    for key, rows in categories:
        yield f', "{key}": ['.encode()
        first = True
        async for item in rows:
            if not first:
                yield b","
            yield json.dumps(item).encode()
            first = False
        yield b"]"
    yield b"}"


@router.post("/export", response_model=VoiceDataExportOut)
async def export_voice_data(
    current_user: User = Depends(get_current_user),
    source: VoiceDataStreamSource = Depends(get_voice_data_repository),
    limiter: RateLimiter = Depends(get_voice_data_export_rate_limiter),
) -> StreamingResponse:
    """Export the learner's voice-derived data: utterances, vocabulary, debriefs,
    and review items. Raw audio is never retained, so it is not — and cannot be —
    part of the export. Streamed (#365): a learner with a large history is never
    fully buffered in memory before the response is sent."""
    await limiter.check(user_rate_limit_key("voice-data-export", current_user.id))
    return StreamingResponse(
        _stream_export_json(source, current_user.id), media_type="application/json"
    )


@router.delete("", response_model=VoiceDataEraseOut)
async def erase_voice_data(
    current_user: User = Depends(get_current_user),
    service: VoiceDataService = Depends(get_voice_data_service),
) -> VoiceDataEraseOut:
    """Erase the learner's voice-derived data: transcripts, debriefs, the session
    records, vocabulary, review items, compiled missions, per-session analytics
    events, the profile memory summary, the speech-derived user fields (CEFR level
    and streak counters, reset to defaults), and the cached turn replies. The
    account, login, consent record, and onboarding settings are kept — this is data
    erasure, not account deletion."""
    deleted = await service.erase(current_user.id)
    return VoiceDataEraseOut(deleted=deleted)
