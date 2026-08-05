"""Unit tests for the surprise-transfer service (#126)."""

import pytest

from app.features.auth.models import User
from app.features.transfer.service import TransferService


class _StubMissions:
    def __init__(self):
        self.seen_source_type = None
        self.seen_content = None

    async def create(self, user, source_type, content):
        self.seen_source_type = source_type
        self.seen_content = content
        return f"mission for {user.email}"  # stand-in; only the call matters here


@pytest.mark.asyncio
async def test_challenge_compiles_a_novel_task_for_the_skill():
    missions = _StubMissions()
    user = User(email="l@x.com", hashed_password="h")

    await TransferService(missions).challenge(user, skill="job_interview")

    # It reuses the mission compiler with a topic directive that NAMES the skill
    # and demands a new, unrehearsed context (transfer, not recall).
    assert missions.seen_source_type == "topic"
    assert "job_interview" in missions.seen_content
    assert "NEW" in missions.seen_content
    assert "no hints" in missions.seen_content.lower()


@pytest.mark.asyncio
async def test_challenge_returns_the_created_mission():
    user = User(email="l@x.com", hashed_password="h")
    result = await TransferService(_StubMissions()).challenge(user, "restaurant")
    assert result == "mission for l@x.com"
