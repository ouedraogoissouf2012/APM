"""Unit tests for MissionService — no DB, no network (fakes only)."""

import pytest

from app.domain.exceptions import NotFoundError
from app.features.auth.models import User
from app.features.missions.compiler import MissionCompiler
from app.features.missions.models import Mission
from app.features.missions.service import MissionService


class _FakeMissionRepo:
    """In-memory mission store (substitutable for the SQLAlchemy repo, LSP)."""

    def __init__(self) -> None:
        self._rows: list[Mission] = []
        self._next_id = 1

    async def add(
        self, user_id, source_type, persona, goal, likely_questions, system_prompt
    ) -> Mission:
        mission = Mission(
            id=self._next_id,
            user_id=user_id,
            source_type=source_type,
            persona=persona,
            goal=goal,
            likely_questions=likely_questions,
            system_prompt=system_prompt,
        )
        self._next_id += 1
        self._rows.append(mission)
        return mission

    async def get_owned(self, mission_id, user_id) -> Mission | None:
        return next((m for m in self._rows if m.id == mission_id and m.user_id == user_id), None)


class _CannedLlm:
    async def complete(self, system_prompt, history):
        return (
            '{"persona": "A recruiter", "goal": "Introduce yourself", '
            '"likely_questions": ["Tell me about yourself"]}'
        )


def _user(user_id: int = 1) -> User:
    return User(
        id=user_id,
        email=f"u{user_id}@b.com",
        hashed_password="x",
        cefr_level="B1",
        native_language="fr",
    )


def _service(repo: _FakeMissionRepo) -> MissionService:
    return MissionService(missions=repo, compiler=MissionCompiler(_CannedLlm()))


@pytest.mark.asyncio
async def test_create_persists_a_compiled_mission():
    repo = _FakeMissionRepo()
    mission = await _service(repo).create(_user(), "offer", "Backend engineer offer")
    assert mission.persona == "A recruiter"
    assert mission.goal == "Introduce yourself"
    assert mission.system_prompt  # computed server-side and stored
    assert "recruiter" in mission.system_prompt.lower()


@pytest.mark.asyncio
async def test_get_returns_own_mission():
    repo = _FakeMissionRepo()
    created = await _service(repo).create(_user(1), "offer", "offer text")
    fetched = await _service(repo).get(created.id, _user(1))
    assert fetched.id == created.id


@pytest.mark.asyncio
async def test_get_rejects_another_users_mission():
    repo = _FakeMissionRepo()
    created = await _service(repo).create(_user(1), "offer", "offer text")
    # A different user must never load it — 404, not the mission.
    with pytest.raises(NotFoundError):
        await _service(repo).get(created.id, _user(2))


@pytest.mark.asyncio
async def test_get_missing_mission_raises_not_found():
    with pytest.raises(NotFoundError):
        await _service(_FakeMissionRepo()).get(999, _user(1))
