"""In-memory repository fakes implementing the repository Protocols.

These are substitutable for the SQLAlchemy implementations (Liskov), letting us
unit-test services with no database.
"""

from datetime import UTC, datetime

from app.features.auth.models import RefreshToken, User
from app.features.conversation.models import Transcript
from app.features.profile.models import LearnerProfile
from app.features.sessions.models import ConversationSession


class InMemoryRefreshTokenRepository:
    def __init__(self) -> None:
        self._by_hash: dict[str, RefreshToken] = {}
        self._seq = 0

    async def create(
        self,
        user_id: int,
        token_hash: str,
        expires_at: datetime,
        *,
        commit: bool = True,
    ) -> RefreshToken:
        self._seq += 1
        token = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        token.id = self._seq
        self._by_hash[token_hash] = token
        return token

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        return self._by_hash.get(token_hash)

    async def lock_by_hash(self, token_hash: str) -> RefreshToken | None:
        return self._by_hash.get(token_hash)

    async def revoke(
        self, token: RefreshToken, revoked_at: datetime, *, commit: bool = True
    ) -> None:
        token.revoked_at = revoked_at

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class InMemorySessionRepository:
    def __init__(self) -> None:
        self._by_id: dict[int, ConversationSession] = {}
        self._seq = 0

    async def get(self, session_id: int) -> ConversationSession | None:
        return self._by_id.get(session_id)

    async def get_active_for_user(self, user_id: int) -> ConversationSession | None:
        return next(
            (s for s in self._by_id.values() if s.user_id == user_id and s.ended_at is None),
            None,
        )

    async def list_recent_for_user(
        self, user_id: int, limit: int
    ) -> list[tuple[ConversationSession, str | None]]:
        sessions = sorted(
            (s for s in self._by_id.values() if s.user_id == user_id),
            key=lambda s: (s.started_at, s.id),
            reverse=True,
        )
        return [(session, None) for session in sessions[:limit]]

    async def add(self, session: ConversationSession) -> ConversationSession:
        self._seq += 1
        session.id = self._seq
        if session.started_at is None:
            session.started_at = datetime.now(UTC)
        self._by_id[session.id] = session
        return session

    async def commit(self) -> None:
        pass


class InMemoryTranscriptRepository:
    def __init__(self) -> None:
        self._by_session: dict[int, Transcript] = {}

    async def save(self, session_id: int, turns: list[dict]) -> Transcript:
        transcript = self._by_session.get(session_id)
        if transcript is None:
            transcript = Transcript(session_id=session_id, turns=turns)
            self._by_session[session_id] = transcript
        else:
            transcript.turns = turns
        return transcript

    async def get_by_session(self, session_id: int) -> Transcript | None:
        return self._by_session.get(session_id)


class InMemoryProfileRepository:
    def __init__(self) -> None:
        self._by_user_id: dict[int, LearnerProfile] = {}

    async def get_by_user_id(self, user_id: int) -> LearnerProfile | None:
        return self._by_user_id.get(user_id)

    async def create(self, profile: LearnerProfile) -> LearnerProfile:
        self._by_user_id[profile.user_id] = profile
        return profile

    async def save(self, profile: LearnerProfile) -> LearnerProfile:
        self._by_user_id[profile.user_id] = profile
        return profile


class InMemoryUserRepository:
    def __init__(self) -> None:
        self._by_id: dict[int, User] = {}
        self._seq = 0

    async def get_by_id(self, user_id: int) -> User | None:
        return self._by_id.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        return next((u for u in self._by_id.values() if u.email == email), None)

    async def create(self, user: User) -> User:
        self._seq += 1
        user.id = self._seq
        self._by_id[user.id] = user
        return user

    async def lock(self, user_id: int) -> User | None:
        # No real locking in memory; behaves like get_by_id.
        return self._by_id.get(user_id)
