"""Conversation-session business logic, with production-grade safeguards.

- Server-side duration (started_at -> now), never trusted from the client.
- Quota anti-race: the user row is locked (SELECT FOR UPDATE) for the whole start
  use case, and only ONE active session per user is allowed.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from app.core import quota
from app.core.engines import ENGINE_FAKE
from app.domain.exceptions import (
    ActiveSessionExistsError,
    NotFoundError,
    QuotaExhaustedError,
)
from app.features.auth.models import User
from app.features.auth.repository import UserRepository
from app.features.conversation.repository import TranscriptRepository
from app.features.missions.repository import MissionRepository
from app.features.sessions.activity import elapsed_minutes, is_stale
from app.features.sessions.models import ConversationSession
from app.features.sessions.ownership import get_owned_session
from app.features.sessions.repository import SessionRepository
from app.features.streaks.logic import StreakState, register_active_day

DEFAULT_HISTORY_PAGE_SIZE = 20
# Offline replay (#431): a client-supplied practice instant older than this
# (or in the future) is ignored so a clock-skewed or hostile client cannot
# rewrite last week’s streak.
_MAX_PRACTICE_SKEW = timedelta(hours=48)


def clamp_practiced_at(raw: datetime | None, *, now: datetime | None = None) -> datetime:
    """Accept a client practice instant only if it is in [now-48h, now]."""
    now = now or datetime.now(UTC)
    if raw is None:
        return now
    if raw.tzinfo is None:
        raw = raw.replace(tzinfo=UTC)
    raw = raw.astimezone(UTC)
    if raw > now or now - raw > _MAX_PRACTICE_SKEW:
        return now
    return raw


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


def _apply_active_day(user: User, today: date) -> None:
    """Apply the pure streak transition to the user's stored streak fields.

    Streak columns default to 0 in the DB, but a User built in memory (tests, or
    before the column default applies) may carry None — treat that as 0 so a turn
    never fails on streak bookkeeping."""
    updated = register_active_day(
        StreakState(
            current_streak=user.current_streak or 0,
            longest_streak=user.longest_streak or 0,
            last_active_date=user.last_active_date,
        ),
        today,
    )
    user.current_streak = updated.current_streak
    user.longest_streak = updated.longest_streak
    user.last_active_date = updated.last_active_date


class SessionService:
    def __init__(
        self,
        sessions: SessionRepository,
        users: UserRepository,
        free_daily_minutes: int,
        transcripts: TranscriptRepository | None = None,
        voice_engine: str = ENGINE_FAKE,
        history_page_size: int = DEFAULT_HISTORY_PAGE_SIZE,
        missions: MissionRepository | None = None,
        inactivity_timeout_minutes: float = 30.0,
        turn_meter_cap_minutes: float = 5.0,
    ) -> None:
        self._sessions = sessions
        self._users = users
        self._free_daily = free_daily_minutes
        self._transcripts = transcripts
        self._voice_engine = voice_engine
        self._history_page_size = history_page_size
        self._missions = missions
        self._inactivity_timeout = inactivity_timeout_minutes
        self._turn_meter_cap = turn_meter_cap_minutes

    async def start(
        self,
        user_id: int,
        mode: str,
        scenario_id: str | None,
        mission_id: int | None = None,
    ) -> ConversationSession:
        # Lock the user row for the whole use case -> serializes concurrent starts.
        user = await self._users.lock(user_id)
        if user is None:
            raise NotFoundError("User not found")
        if quota.remaining_minutes(user, self._free_daily, datetime.now(UTC).date()) <= 0:
            raise QuotaExhaustedError("Daily free quota exhausted")
        active = await self._sessions.get_active_for_user(user_id)
        if active is not None:
            # Lazy reaper (#119): a session abandoned without /end would lock the
            # user out forever. If it has been idle past the timeout, auto-close it
            # (billing its usage) so this start can proceed; otherwise it is a real
            # concurrent session and we still reject.
            now = datetime.now(UTC)
            if is_stale(_as_utc(active.last_activity_at), now, self._inactivity_timeout):
                await self._close_session(active, user, now)
                if quota.remaining_minutes(user, self._free_daily, now.date()) <= 0:
                    # Re-check quota AFTER the reap (#301): the check above ran
                    # before the abandoned session's residual usage was billed onto
                    # `user` (same locked, in-memory object `_close_session` just
                    # updated), so it can pass on a stale balance the reap alone
                    # pushes over the daily cap. Commit the reap's billing before
                    # rejecting — it is real usage that happened, and letting the
                    # exception unwind uncommitted would both lose it (get_db()
                    # rolls back the whole request on an unhandled exception) and
                    # leave the abandoned session "active" forever, reintroducing
                    # the #119 lockout the reaper exists to prevent. When quota is
                    # still OK after the reap, we deliberately do NOT commit here:
                    # the user row stays locked ("for the whole use case", per the
                    # class docstring) all the way to the single commit below,
                    # instead of releasing it mid-function and reopening a window
                    # for a second concurrent start() to slip in before the new
                    # session is created.
                    await self._sessions.commit()
                    raise QuotaExhaustedError("Daily free quota exhausted")
            else:
                raise ActiveSessionExistsError("A session is already in progress")

        # Never trust the client's claim to own the mission: re-check here. A
        # missing/foreign mission id is a 404 (does not reveal existence).
        if mission_id is not None and not await self._owns_mission(mission_id, user_id):
            raise NotFoundError("Mission not found")

        session = ConversationSession(
            user_id=user_id,
            mode=mode,
            scenario_id=scenario_id,
            mission_id=mission_id,
            # Set explicitly (not only via server_default) so last_activity_at is
            # never None on the in-memory object between add() and refresh.
            started_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
            voice_engine=self._voice_engine,  # record the engine that served it
        )
        await self._sessions.add(session)
        await self._sessions.commit()
        return session

    async def _owns_mission(self, mission_id: int, user_id: int) -> bool:
        if self._missions is None:
            return False
        return await self._missions.get_owned(mission_id, user_id) is not None

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

    async def end(
        self, session_id: int, user_id: int, *, now: datetime | None = None
    ) -> ConversationSession:
        session = await get_owned_session(self._sessions, session_id, user_id)
        if session.ended_at is not None:
            return session  # idempotent: ending an already-ended session is a no-op

        now = now or datetime.now(UTC)
        # Lock the user row like start()/record_turn_activity (#228): _close_session
        # bills the quota — a read-modify-write on minutes_used_today — so a plain get
        # would lost-update against a concurrent last-turn metering. FOR UPDATE
        # serialises end() with those paths (same shared DB session -> commit releases).
        user = await self._users.lock(user_id)
        # Re-read the session AFTER the lock (#258): a last-turn metering may have
        # advanced last_activity_at (and billed up to it) between the read above and
        # the lock. Without this refresh, _close_session computes the residual from a
        # stale last_activity_at and bills that turn's interval a second time.
        await self._sessions.refresh(session)
        if session.ended_at is not None:
            return session  # ended concurrently between our first read and the lock
        await self._close_session(session, user, now)
        await self._sessions.commit()
        return session

    async def record_turn_activity(
        self, session_id: int, user_id: int, *, now: datetime | None = None
    ) -> None:
        """Meter the quota per turn (#119) and mark the session active NOW.

        Called on every conversation turn so usage accrues even if the client
        never calls /end — closing the "unlimited free turns" hole. The charge is
        the gap since the last activity, capped so one long pause can't over-bill.
        Best-effort: a metering failure must never break a turn, so callers ignore
        errors. `now` is injectable so the day boundary is deterministically testable.

        The active DAY is taken from the UTC calendar date, not the server's local
        `date.today()` — so the streak no longer depends on where the server is
        deployed. Tracked debt: a truly per-learner day boundary needs a stored user
        timezone (a learner far from UTC near midnight can still be off by one day);
        that field/capture is out of scope here and left as follow-up."""
        session = await self._sessions.get(session_id)
        if session is None or session.user_id != user_id or session.ended_at is not None:
            return
        now = now or datetime.now(UTC)
        today = now.date()
        minutes = elapsed_minutes(_as_utc(session.last_activity_at), now, cap=self._turn_meter_cap)
        # Lock the user row (like start()/end()) BEFORE mutating the session
        # (#381): quota minutes and streak counters are a read-modify-write, so a
        # plain get would let concurrent turns lost-update each other (#188) —
        # FOR UPDATE serialises them. The ordering matters as much as the lock
        # itself: dirtying `session.last_activity_at` first would make the
        # lock() call's autoflush (autoflush defaults to True) emit
        # `UPDATE sessions ...` BEFORE `SELECT users ... FOR UPDATE`, i.e. a
        # SESSION->USER acquisition order — the reverse of start()/end(), which
        # lock the user while nothing is dirty yet and only mutate the session
        # afterwards (USER->SESSION). Two connections contending on the same
        # (user, session) pair in opposite lock order is a classic AB-BA
        # deadlock: locking the user here first, before any session mutation,
        # keeps every path on the same USER->SESSION order.
        user = await self._users.lock(user_id)
        # #427: same as end() (#258) — a concurrent /end may have billed the
        # residual and set ended_at between our first read and this lock.
        await self._sessions.refresh(session)
        if session.ended_at is not None:
            return
        session.last_activity_at = now
        if user is not None:
            if minutes > 0:
                quota.record_usage(user, minutes, today)
            # Habit tracking (#118): any turn today counts as an active day, even
            # a sub-minute one — showing up is the point of a streak.
            _apply_active_day(user, today)
        await self._sessions.commit()

    async def _close_session(
        self, session: ConversationSession, user: User | None, now: datetime
    ) -> None:
        """Mark a session ended and bill the total server-side duration. Shared by
        the explicit /end and the lazy reaper. Note: per-turn metering already
        charged most of it; the small residual since the last turn is billed here.
        To avoid double-charging the whole session, we bill only the gap since the
        last recorded activity."""
        residual = elapsed_minutes(_as_utc(session.last_activity_at), now, cap=self._turn_meter_cap)
        session.ended_at = now
        session.duration_minutes = max(
            0.0, (now - _as_utc(session.started_at)).total_seconds() / 60.0
        )
        if user is not None and residual > 0:
            quota.record_usage(user, residual, now.date())

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
