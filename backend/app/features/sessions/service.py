"""Conversation-session business logic, with production-grade safeguards.

- Server-side duration (started_at -> now), never trusted from the client.
- Quota anti-race: the user row is locked (SELECT FOR UPDATE) for the whole start
  use case, and only ONE active session per user is allowed.
- room_name uses a UUID (no per-second collision).
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import uuid4

from app.core import quota
from app.core.engines import ENGINE_FAKE
from app.core.livekit import LiveKitRoomTokenIssuer, RoomTokenIssuer
from app.domain.exceptions import (
    ActiveSessionExistsError,
    NotFoundError,
    QuotaExhaustedError,
)
from app.features.auth.repository import UserRepository
from app.features.conversation.repository import TranscriptRepository
from app.features.sessions.models import ConversationSession
from app.features.sessions.ownership import get_owned_session
from app.features.sessions.repository import SessionRepository

DEFAULT_HISTORY_PAGE_SIZE = 20


@dataclass
class StartedSession:
    session: ConversationSession
    livekit_token: str


@dataclass(frozen=True)
class ActiveSession:
    session: ConversationSession
    turns: list[dict]


@dataclass(frozen=True)
class SessionHistoryItem:
    id: int
    mode: str
    scenario_id: str | None
    started_at: datetime
    duration_minutes: float | None
    cefr_estimate: str | None


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class SessionService:
    def __init__(
        self,
        sessions: SessionRepository,
        users: UserRepository,
        free_daily_minutes: int,
        transcripts: TranscriptRepository | None = None,
        token_issuer: RoomTokenIssuer | None = None,
        voice_engine: str = ENGINE_FAKE,
        history_page_size: int = DEFAULT_HISTORY_PAGE_SIZE,
    ) -> None:
        self._sessions = sessions
        self._users = users
        self._free_daily = free_daily_minutes
        self._transcripts = transcripts
        self._token_issuer = token_issuer or LiveKitRoomTokenIssuer()
        self._voice_engine = voice_engine
        self._history_page_size = history_page_size

    async def start(self, user_id: int, mode: str, scenario_id: str | None) -> StartedSession:
        # Lock the user row for the whole use case -> serializes concurrent starts.
        user = await self._users.lock(user_id)
        if user is None:
            raise NotFoundError("User not found")
        if quota.remaining_minutes(user, self._free_daily, date.today()) <= 0:
            raise QuotaExhaustedError("Daily free quota exhausted")
        if await self._sessions.get_active_for_user(user_id) is not None:
            raise ActiveSessionExistsError("A session is already in progress")

        session = ConversationSession(
            user_id=user_id,
            mode=mode,
            scenario_id=scenario_id,
            room_name=f"apm-{user_id}-{uuid4().hex}",
            voice_engine=self._voice_engine,  # record the engine that served it
        )
        await self._sessions.add(session)
        await self._sessions.commit()

        token = self._token_issuer.issue(identity=f"user-{user_id}", room=session.room_name)
        return StartedSession(session=session, livekit_token=token)

    async def active(self, user_id: int) -> ActiveSession | None:
        """The user's in-progress session with its transcript so far, or None.

        Enables resuming a conversation the client lost track of, instead of
        being locked out by the one-active-session rule enforced in `start`.
        """
        session = await self._sessions.get_active_for_user(user_id)
        if session is None:
            return None
        turns: list[dict] = []
        if self._transcripts is not None:
            transcript = await self._transcripts.get_by_session(session.id)
            if transcript is not None:
                turns = list(transcript.turns)
        return ActiveSession(session=session, turns=turns)

    async def end(self, session_id: int, user_id: int) -> ConversationSession:
        session = await get_owned_session(self._sessions, session_id, user_id)
        if session.ended_at is not None:
            return session  # idempotent: ending an already-ended session is a no-op

        now = datetime.now(UTC)
        duration = max(0.0, (now - _as_utc(session.started_at)).total_seconds() / 60.0)
        session.ended_at = now
        session.duration_minutes = duration

        user = await self._users.get_by_id(user_id)
        if user is not None:
            quota.record_usage(user, duration, date.today())
        await self._sessions.commit()
        return session

    async def history(self, user_id: int, limit: int | None = None) -> list[SessionHistoryItem]:
        page_size = limit if limit is not None else self._history_page_size
        rows = await self._sessions.list_recent_for_user(user_id=user_id, limit=page_size)
        return [
            SessionHistoryItem(
                id=session.id,
                mode=session.mode,
                scenario_id=session.scenario_id,
                started_at=session.started_at,
                duration_minutes=session.duration_minutes,
                cefr_estimate=cefr,
            )
            for session, cefr in rows
        ]
