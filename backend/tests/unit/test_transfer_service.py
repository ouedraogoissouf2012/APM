"""Unit tests for the surprise-transfer service (#126)."""

import pytest

from app.features.auth.models import User
from app.features.transfer.service import TransferService


class _StubMissions:
    def __init__(self):
        self.seen_source_type = None
        self.seen_content = None
        self.seen_directive = None

    async def create(self, user, source_type, content, *, directive=""):
        self.seen_source_type = source_type
        self.seen_content = content
        self.seen_directive = directive
        return f"mission for {user.email}"  # stand-in; only the call matters here


@pytest.mark.asyncio
async def test_challenge_passes_the_skill_as_content_and_the_brief_as_a_trusted_directive():
    missions = _StubMissions()
    user = User(email="l@x.com", hashed_password="h")

    await TransferService(missions).challenge(user, skill="job_interview")

    # The skill is the (untrusted) content; the transfer brief demanding a new,
    # unrehearsed context rides the TRUSTED directive channel — not the content.
    assert missions.seen_content == "job_interview"
    assert missions.seen_source_type == "freeform"
    assert "NEW" in missions.seen_directive
    assert "no hints" in missions.seen_directive.lower()
    assert "job_interview" not in missions.seen_directive  # skill isn't baked in


@pytest.mark.asyncio
async def test_challenge_returns_the_created_mission():
    user = User(email="l@x.com", hashed_password="h")
    result = await TransferService(_StubMissions()).challenge(user, "restaurant")
    assert result == "mission for l@x.com"
