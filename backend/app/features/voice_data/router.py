import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rate_limit import RateLimiter, user_rate_limit_key
from app.database import get_db
from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.voice_data.dependencies import (
    get_voice_data_export_rate_limiter,
    get_voice_data_service,
)
from app.features.voice_data.repository import VoiceDataExportRepository
from app.features.voice_data.schemas import VoiceDataEraseOut, VoiceDataExportOut
from app.features.voice_data.service import VoiceDataService

router = APIRouter(prefix="/me/voice-data", tags=["voice-data"])


async def _assemble_export_json(
    categories: tuple[tuple[str, AsyncIterator[dict]], ...],
) -> AsyncIterator[bytes]:
    """Assemble the SAME JSON document `VoiceDataExportOut` describes, one
    category/row at a time (#365) — never holding the learner's full
    voice-derived history as one Python list. The bytes sent over the wire are
    byte-for-byte a normal JSON body: chunked transfer encoding is transparent
    to any HTTP client (incl. the mobile app's plain `jsonDecode` on the
    received body), so this is not a contract change. DB-agnostic on purpose:
    takes already-built async iterators, so it is unit-testable with fakes.
    """
    yield b'{"raw_audio_retained": false'
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


async def _stream_export_json(
    repo: VoiceDataExportRepository, user_id: int
) -> AsyncIterator[bytes]:
    categories: tuple[tuple[str, AsyncIterator[dict]], ...] = (
        ("utterances", repo.stream_utterances(user_id)),
        ("vocabulary", repo.stream_vocabulary(user_id)),
        ("debriefs", repo.stream_debriefs(user_id)),
        ("review_items", repo.stream_review_items(user_id)),
    )
    async for chunk in _assemble_export_json(categories):
        yield chunk


@router.post("/export", response_model=VoiceDataExportOut)
async def export_voice_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limiter: RateLimiter = Depends(get_voice_data_export_rate_limiter),
) -> StreamingResponse:
    """Export the learner's voice-derived data: utterances, vocabulary, debriefs,
    and review items. Raw audio is never retained, so it is not — and cannot be —
    part of the export. Streamed AND paginated (#365, #389): a learner with a
    large history is never fully buffered in memory, and the connection used to
    fetch each page is released back to the pool between pages instead of being
    pinned for the whole client-paced download."""
    await limiter.check(user_rate_limit_key("voice-data-export", current_user.id))
    # Capture the id BEFORE releasing the session: rollback() expires every ORM object
    # attached to `db` (including current_user, loaded by get_current_user), so reading
    # current_user.id afterwards would trigger a lazy reload on the now-released
    # connection — in a sync attribute access with no greenlet (MissingGreenlet).
    user_id = current_user.id
    # Release the request-scoped connection BEFORE streaming (#389): get_current_user
    # already queried on `db`, so this session is holding a pooled connection. Without
    # this rollback it would stay checked out for the ENTIRE client-paced download
    # (get_db only closes it once the StreamingResponse completes), pinning one of the
    # ~20 pool slots per slow reader. rollback() ends that transaction and returns the
    # connection to the pool; `db` is never queried again below.
    await db.rollback()
    # Build a fresh sessionmaker from the SAME bind (the engine, unaffected by the
    # rollback) so every page runs against whichever engine this request resolved to
    # (prod, or the test DB via dependency_overrides on get_db) and each page checks
    # out a connection only for the duration of its own short-lived session.
    page_sessions = async_sessionmaker(bind=db.bind, expire_on_commit=False)
    repo = VoiceDataExportRepository(page_sessions)
    return StreamingResponse(_stream_export_json(repo, user_id), media_type="application/json")


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
