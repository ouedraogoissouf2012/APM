"""Unit tests for the before/after proof service (#126)."""

import pytest

from app.features.proof.service import ProofService, SessionErrors


class _StubSource:
    def __init__(self, sessions):
        self._sessions = sessions

    async def sessions_for_skill(self, user_id, skill):
        return self._sessions


def _s(sid, cefr, errors, day=1):
    return SessionErrors(
        session_id=sid, started_at=f"2026-08-0{day}T10:00:00Z", cefr=cefr, error_counts=errors
    )


@pytest.mark.asyncio
async def test_no_proof_with_fewer_than_two_sessions():
    assert await ProofService(_StubSource([])).proof(1, "job_interview") is None
    assert (
        await ProofService(_StubSource([_s(1, "A2", {"verb_tense": 2})])).proof(1, "job_interview")
        is None
    )


@pytest.mark.asyncio
async def test_reports_resolved_error_types():
    baseline = _s(1, "A2", {"verb_tense": 3, "article": 1}, day=1)
    latest = _s(2, "B1", {"article": 1}, day=5)  # verb_tense gone
    proof = await ProofService(_StubSource([baseline, latest])).proof(1, "job_interview")

    assert proof is not None
    assert proof.baseline_session_id == 1
    assert proof.latest_session_id == 2
    assert proof.baseline_cefr == "A2"
    assert proof.latest_cefr == "B1"
    assert proof.resolved == ["verb_tense"]  # article unchanged, not resolved
    assert proof.new_or_worse == []


@pytest.mark.asyncio
async def test_partial_reduction_counts_as_resolved():
    baseline = _s(1, "A2", {"verb_tense": 3})
    latest = _s(2, "A2", {"verb_tense": 1})  # fewer, not zero
    proof = await ProofService(_StubSource([baseline, latest])).proof(1, "s")
    assert proof.resolved == ["verb_tense"]


@pytest.mark.asyncio
async def test_reports_regressions_honestly():
    baseline = _s(1, "B1", {"verb_tense": 1})
    latest = _s(2, "B1", {"verb_tense": 1, "preposition": 2})  # new issue
    proof = await ProofService(_StubSource([baseline, latest])).proof(1, "s")
    assert proof.resolved == []
    assert proof.new_or_worse == ["preposition"]


@pytest.mark.asyncio
async def test_uses_first_and_last_when_more_than_two_sessions():
    sessions = [
        _s(1, "A1", {"verb_tense": 3}, day=1),
        _s(2, "A2", {"verb_tense": 2}, day=3),
        _s(3, "B1", {}, day=7),
    ]
    proof = await ProofService(_StubSource(sessions)).proof(1, "s")
    assert proof.baseline_session_id == 1
    assert proof.latest_session_id == 3
    assert proof.resolved == ["verb_tense"]
