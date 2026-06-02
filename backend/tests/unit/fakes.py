"""In-memory repository fakes implementing the repository Protocols.

These are substitutable for the SQLAlchemy implementations (Liskov), letting us
unit-test services with no database.
"""

from app.models.learner_profile import LearnerProfile
from app.models.user import User


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
