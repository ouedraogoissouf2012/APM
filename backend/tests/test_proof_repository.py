"""Repository-level tests for SqlAlchemyProofDataSource (#363): the fix
replaces "fetch every session on the skill" with two targeted edge queries.
These tests pin the exact shape/values returned for 0, 1, and 3+ sessions —
proving no semantics were lost by the rewrite."""

from datetime import UTC, datetime, timedelta

import pytest

from app.features.auth.models import User
from app.features.conversation.messages import ROLE_ASSISTANT, ROLE_USER
from app.features.conversation.repository import SqlAlchemyTranscriptRepository
from app.features.debrief.repository import SqlAlchemyDebriefRepository
from app.features.proof.repository import SqlAlchemyProofDataSource
from app.features.sessions.models import ConversationSession


async def _user(db_session) -> User:
    user = User(email="proofrepo@b.com", hashed_password="x", native_language="fr")
    db_session.add(user)
    await db_session.flush()
    return user


def _err(t):
    return {"error_type": t, "correction": "c", "original": "o", "rule": "r"}


async def _session_with_debrief(
    db_session, user_id, *, scenario, started_at, cefr, errors, learner_turns=0
):
    session = ConversationSession(
        user_id=user_id, mode="scenario", scenario_id=scenario, started_at=started_at
    )
    db_session.add(session)
    await db_session.flush()
    if learner_turns:
        transcript = []
        for _ in range(learner_turns):
            transcript.append({"role": ROLE_ASSISTANT, "content": "?"})
            transcript.append({"role": ROLE_USER, "content": "..."})
        await SqlAlchemyTranscriptRepository(db_session).save(session.id, transcript)
    await SqlAlchemyDebriefRepository(db_session).save(session.id, cefr, "s", errors)
    await db_session.commit()
    return session.id


@pytest.mark.asyncio
async def test_returns_empty_list_when_no_session_has_a_debrief(db_session):
    user = await _user(db_session)
    source = SqlAlchemyProofDataSource(db_session)

    assert await source.sessions_for_skill(user.id, "job_interview") == []


@pytest.mark.asyncio
async def test_returns_a_single_element_for_exactly_one_session(db_session):
    user = await _user(db_session)
    now = datetime.now(UTC)
    sid = await _session_with_debrief(
        db_session,
        user.id,
        scenario="job_interview",
        started_at=now,
        cefr="A2",
        errors=[_err("verb_tense")],
        learner_turns=3,
    )
    source = SqlAlchemyProofDataSource(db_session)

    sessions = await source.sessions_for_skill(user.id, "job_interview")

    assert len(sessions) == 1
    assert sessions[0].session_id == sid
    assert sessions[0].cefr == "A2"
    assert sessions[0].error_counts == {"verb_tense": 1}
    assert sessions[0].turn_count == 3


@pytest.mark.asyncio
async def test_returns_baseline_and_latest_only_with_three_or_more_sessions(db_session):
    user = await _user(db_session)
    now = datetime.now(UTC)
    first = await _session_with_debrief(
        db_session,
        user.id,
        scenario="job_interview",
        started_at=now,
        cefr="A1",
        errors=[_err("verb_tense"), _err("verb_tense")],
        learner_turns=10,
    )
    middle = await _session_with_debrief(
        db_session,
        user.id,
        scenario="job_interview",
        started_at=now + timedelta(days=3),
        cefr="A2",
        errors=[_err("article"), _err("article"), _err("article")],
        learner_turns=10,
    )
    last = await _session_with_debrief(
        db_session,
        user.id,
        scenario="job_interview",
        started_at=now + timedelta(days=7),
        cefr="B1",
        errors=[],
        learner_turns=10,
    )

    sessions = await SqlAlchemyProofDataSource(db_session).sessions_for_skill(
        user.id, "job_interview"
    )

    assert [s.session_id for s in sessions] == [first, last]
    assert middle not in [s.session_id for s in sessions]
    assert sessions[0].cefr == "A1"
    assert sessions[-1].cefr == "B1"


@pytest.mark.asyncio
async def test_excludes_sessions_on_a_different_skill_or_without_a_debrief(db_session):
    user = await _user(db_session)
    now = datetime.now(UTC)
    # Different scenario -> not comparable to job_interview (scope note in the
    # repository docstring): must not become baseline/latest for it.
    await _session_with_debrief(
        db_session, user.id, scenario="restaurant", started_at=now, cefr="A2", errors=[]
    )
    # No debrief at all (the INNER join on Debrief excludes it).
    no_debrief = ConversationSession(
        user_id=user.id, mode="scenario", scenario_id="job_interview", started_at=now
    )
    db_session.add(no_debrief)
    await db_session.commit()

    sessions = await SqlAlchemyProofDataSource(db_session).sessions_for_skill(
        user.id, "job_interview"
    )

    assert sessions == []
