"""Terminal write of a conversation turn (#448).

Extracted from ConversationTurnService so that class stays the LLM/stream
orchestrator and this module owns transcript + meter on a short-lived session.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime

from app.core import metrics
from app.core.llm.messages import ROLE_ASSISTANT, ROLE_USER
from app.features.auth.models import User
from app.features.conversation.repository import TranscriptRepository
from app.features.sessions.service import clamp_practiced_at


@dataclass(frozen=True)
class TurnPersistence:
    """A fresh, short-lived unit of work for the TERMINAL write of a turn (#399)."""

    transcripts: TranscriptRepository
    meter: Callable[[int, int], Awaitable[None]] | None


PersistenceScopeFactory = Callable[[], AbstractAsyncContextManager[TurnPersistence]]


async def persist_turn(
    scope: TurnPersistence,
    session_id: int,
    user: User,
    turns: list[dict],
    text: str,
    reply: str,
    *,
    practiced_at: datetime | None = None,
    transcript_max_messages: int = 0,
) -> list[dict]:
    turns = [
        *turns,
        {"role": ROLE_USER, "content": text},
        {"role": ROLE_ASSISTANT, "content": reply},
    ]
    if transcript_max_messages > 0 and len(turns) > transcript_max_messages:
        turns = turns[-transcript_max_messages:]
    await scope.transcripts.save(session_id, turns, commit=False)
    if scope.meter is not None:
        try:
            now = clamp_practiced_at(practiced_at)
            try:
                await scope.meter(session_id, user.id, now=now)  # type: ignore[call-arg]
            except TypeError:
                await scope.meter(session_id, user.id)
        except Exception:
            metrics.inc(metrics.METER_FAILURES)
            logging.getLogger(__name__).warning(
                "Per-turn quota metering failed for session %s", session_id, exc_info=True
            )
            await scope.transcripts.commit()
    else:
        await scope.transcripts.commit()
    return turns


@contextlib.asynccontextmanager
async def null_persistence(scope: TurnPersistence) -> AsyncIterator[TurnPersistence]:
    yield scope
