import json
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rate_limit import RateLimiter, user_rate_limit_key
from app.database import get_db
from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.conversation.messages import ROLE_USER
from app.features.conversation.models import Transcript
from app.features.debrief.models import Debrief
from app.features.review.models import ReviewItem
from app.features.sessions.models import ConversationSession
from app.features.vocabulary.models import VocabularyEntry
from app.features.voice_data.dependencies import (
    get_voice_data_export_rate_limiter,
    get_voice_data_service,
)
from app.features.voice_data.schemas import VoiceDataEraseOut, VoiceDataExportOut
from app.features.voice_data.service import VoiceDataService

router = APIRouter(prefix="/me/voice-data", tags=["voice-data"])

# Rows per page (#389). Each page opens its OWN short-lived DB session (see
# _keyset_pages), so the pooled connection is released back to the pool BETWEEN
# pages while the client reads — never pinned for the whole client-paced
# download, unlike the single request-scoped session #365/#377 originally used.
# Not in Settings: config.py is outside this ticket's territory in this
# coordinated wave.
_EXPORT_PAGE_SIZE = 200


async def _keyset_pages(
    sessionmaker: async_sessionmaker[AsyncSession],
    fetch_page: Callable[[AsyncSession, Any], Awaitable[Sequence[Any]]],
    cursor_of: Callable[[Any], Any],
    *,
    page_size: int,
) -> AsyncIterator[Any]:
    """Generic keyset-paginated fetch (#389): the core of the fix.

    Each loop iteration opens a FRESH, short-lived session, awaits `fetch_page`
    on it, and closes it (the `async with` exit) BEFORE yielding any row from
    that page. So while the caller (here, the ASGI layer sending bytes at the
    client's TCP-backpressured pace) is consuming a page's rows, no DB
    connection is checked out at all — only during the brief page fetch itself.
    `fetch_page(session, cursor)` receives the previous page's cursor (None for
    the first page) and must return at most `page_size` rows in an order for
    which `cursor_of` on the last row is a valid resume point (a strictly
    increasing keyset column, or tuple of columns).
    """
    cursor: Any = None
    while True:
        async with sessionmaker() as session:
            rows = await fetch_page(session, cursor)
        if not rows:
            return
        for row in rows:
            yield row
        cursor = cursor_of(rows[-1])
        if len(rows) < page_size:
            return


async def _stream_utterances_paginated(
    sessionmaker: async_sessionmaker[AsyncSession], user_id: int
) -> AsyncIterator[dict]:
    async def fetch_page(session: AsyncSession, cursor: Any) -> Sequence[Any]:
        stmt = (
            select(ConversationSession.id, ConversationSession.started_at, Transcript.turns)
            .join(Transcript, Transcript.session_id == ConversationSession.id)
            .where(ConversationSession.user_id == user_id)
        )
        if cursor is not None:
            stmt = stmt.where(
                tuple_(ConversationSession.started_at, ConversationSession.id) > tuple_(*cursor)
            )
        stmt = stmt.order_by(
            ConversationSession.started_at.asc(), ConversationSession.id.asc()
        ).limit(_EXPORT_PAGE_SIZE)
        return (await session.execute(stmt)).all()

    async for session_id, started_at, turns in _keyset_pages(
        sessionmaker, fetch_page, lambda row: (row[1], row[0]), page_size=_EXPORT_PAGE_SIZE
    ):
        for turn in turns or []:
            if isinstance(turn, dict) and turn.get("role") == ROLE_USER:
                yield {
                    "session_id": session_id,
                    "started_at": started_at.isoformat(),
                    "text": str(turn.get("content", "")),
                }


async def _stream_debriefs_paginated(
    sessionmaker: async_sessionmaker[AsyncSession], user_id: int
) -> AsyncIterator[dict]:
    async def fetch_page(session: AsyncSession, cursor: Any) -> Sequence[Any]:
        stmt = (
            select(
                ConversationSession.id,
                ConversationSession.started_at,
                Debrief.cefr_estimate,
                Debrief.summary,
                Debrief.errors,
            )
            .join(Debrief, Debrief.session_id == ConversationSession.id)
            .where(ConversationSession.user_id == user_id)
        )
        if cursor is not None:
            stmt = stmt.where(
                tuple_(ConversationSession.started_at, ConversationSession.id) > tuple_(*cursor)
            )
        stmt = stmt.order_by(
            ConversationSession.started_at.asc(), ConversationSession.id.asc()
        ).limit(_EXPORT_PAGE_SIZE)
        return (await session.execute(stmt)).all()

    async for session_id, started_at, cefr_estimate, summary, errors in _keyset_pages(
        sessionmaker, fetch_page, lambda row: (row[1], row[0]), page_size=_EXPORT_PAGE_SIZE
    ):
        yield {
            "session_id": session_id,
            "started_at": started_at.isoformat(),
            "cefr_estimate": cefr_estimate,
            "summary": summary,
            "errors": errors or [],
        }


async def _stream_vocabulary_paginated(
    sessionmaker: async_sessionmaker[AsyncSession], user_id: int
) -> AsyncIterator[dict]:
    async def fetch_page(session: AsyncSession, cursor: Any) -> Sequence[Any]:
        stmt = select(VocabularyEntry).where(VocabularyEntry.user_id == user_id)
        if cursor is not None:
            stmt = stmt.where(VocabularyEntry.id > cursor)
        stmt = stmt.order_by(VocabularyEntry.id.asc()).limit(_EXPORT_PAGE_SIZE)
        return (await session.scalars(stmt)).all()

    async for entry in _keyset_pages(
        sessionmaker, fetch_page, lambda e: e.id, page_size=_EXPORT_PAGE_SIZE
    ):
        yield {"word": entry.word, "translation": entry.translation, "example": entry.example}


async def _stream_review_items_paginated(
    sessionmaker: async_sessionmaker[AsyncSession], user_id: int
) -> AsyncIterator[dict]:
    async def fetch_page(session: AsyncSession, cursor: Any) -> Sequence[Any]:
        stmt = select(ReviewItem).where(ReviewItem.user_id == user_id)
        if cursor is not None:
            stmt = stmt.where(ReviewItem.id > cursor)
        stmt = stmt.order_by(ReviewItem.id.asc()).limit(_EXPORT_PAGE_SIZE)
        return (await session.scalars(stmt)).all()

    async for item in _keyset_pages(
        sessionmaker, fetch_page, lambda r: r.id, page_size=_EXPORT_PAGE_SIZE
    ):
        yield {
            "error_type": item.error_type,
            "latest_correction": item.latest_correction,
            "stage": item.stage,
            "status": item.status,
            "next_review_at": item.next_review_at.isoformat() if item.next_review_at else None,
        }


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
    sessionmaker: async_sessionmaker[AsyncSession], user_id: int
) -> AsyncIterator[bytes]:
    categories: tuple[tuple[str, AsyncIterator[dict]], ...] = (
        ("utterances", _stream_utterances_paginated(sessionmaker, user_id)),
        ("vocabulary", _stream_vocabulary_paginated(sessionmaker, user_id)),
        ("debriefs", _stream_debriefs_paginated(sessionmaker, user_id)),
        ("review_items", _stream_review_items_paginated(sessionmaker, user_id)),
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
    # `db` is read for its bind (the engine) only — never queried directly, so
    # it never itself checks out a pooled connection (SQLAlchemy sessions
    # acquire a connection lazily, on first statement). Building a fresh
    # sessionmaker from that SAME bind means every page below runs against
    # whichever engine this request resolved to (prod, or the test DB via
    # dependency_overrides on get_db) without hardcoding either one.
    page_sessions = async_sessionmaker(bind=db.bind, expire_on_commit=False)
    return StreamingResponse(
        _stream_export_json(page_sessions, current_user.id), media_type="application/json"
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
