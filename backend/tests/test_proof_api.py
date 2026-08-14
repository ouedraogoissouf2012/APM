"""Integration tests for GET /me/proof/{skill} (#126)."""

import pytest

from app.core.llm.messages import ROLE_ASSISTANT, ROLE_USER
from app.features.conversation.repository import SqlAlchemyTranscriptRepository
from app.features.debrief.repository import SqlAlchemyDebriefRepository


async def _auth(client):
    reg = await client.post("/auth/register", json={"email": "pf@b.com", "password": "s3cret!pass"})
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


async def _session_with_debrief(client, db_session, headers, *, scenario, cefr, errors, turns=0):
    start = await client.post(
        "/sessions/start",
        headers=headers,
        json={"mode": "scenario", "scenario_id": scenario},
    )
    session_id = start.json()["session_id"]
    await client.post(f"/sessions/{session_id}/end", headers=headers)
    if turns:
        # `turns` learner turns (interleaved with the assistant) so proof can
        # normalise error counts by session length.
        transcript = []
        for _ in range(turns):
            transcript.append({"role": ROLE_ASSISTANT, "content": "?"})
            transcript.append({"role": ROLE_USER, "content": "..."})
        await SqlAlchemyTranscriptRepository(db_session).save(session_id, transcript)
    await SqlAlchemyDebriefRepository(db_session).save(session_id, cefr, "s", errors)
    return session_id


def _err(t):
    return {"error_type": t, "correction": "c", "original": "o", "rule": "r"}


@pytest.mark.asyncio
async def test_no_proof_until_two_sessions(client, db_session):
    headers = await _auth(client)
    await _session_with_debrief(
        client,
        db_session,
        headers,
        scenario="job_interview",
        cefr="A2",
        errors=[_err("verb_tense")],
    )
    resp = await client.get("/me/proof/job_interview", headers=headers)
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_proof_reports_resolved_error_types(client, db_session):
    headers = await _auth(client)
    b = await _session_with_debrief(
        client,
        db_session,
        headers,
        scenario="job_interview",
        cefr="A2",
        errors=[_err("verb_tense"), _err("verb_tense"), _err("article")],
    )
    latest = await _session_with_debrief(
        client, db_session, headers, scenario="job_interview", cefr="B1", errors=[_err("article")]
    )

    resp = await client.get("/me/proof/job_interview", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["baseline_session_id"] == b
    assert body["latest_session_id"] == latest
    assert body["baseline_cefr"] == "A2"
    assert body["latest_cefr"] == "B1"
    assert body["resolved"] == ["verb_tense"]  # article unchanged
    assert body["improved"] == []
    assert body["new_or_worse"] == []


@pytest.mark.asyncio
async def test_proof_normalises_by_session_length(client, db_session):
    # Same raw count (2 verb_tense) but the latest session is a quarter as long:
    # per turn the rate went UP, so it reads as worse, not resolved — and the turn
    # counts are surfaced so the UI can show the basis.
    headers = await _auth(client)
    await _session_with_debrief(
        client,
        db_session,
        headers,
        scenario="job_interview",
        cefr="A2",
        errors=[_err("verb_tense"), _err("verb_tense")],
        turns=20,
    )
    await _session_with_debrief(
        client,
        db_session,
        headers,
        scenario="job_interview",
        cefr="A2",
        errors=[_err("verb_tense"), _err("verb_tense")],
        turns=5,
    )

    body = (await client.get("/me/proof/job_interview", headers=headers)).json()
    assert body["baseline_turns"] == 20
    assert body["latest_turns"] == 5
    assert body["new_or_worse"] == ["verb_tense"]
    assert body["resolved"] == [] and body["improved"] == []


@pytest.mark.asyncio
async def test_proof_uses_baseline_and_latest_ignoring_middle_sessions(client, db_session):
    """#363: the repository now fetches only the earliest/latest session with a
    debrief via two targeted queries, instead of every session on the skill.
    With 3+ sessions, the middle one(s) must still be correctly ignored — same
    output as the old 'fetch everything, use sessions[0]/sessions[-1]' code."""
    headers = await _auth(client)
    first = await _session_with_debrief(
        client,
        db_session,
        headers,
        scenario="job_interview",
        cefr="A1",
        errors=[_err("verb_tense"), _err("verb_tense")],
        turns=10,
    )
    # Middle session: if it leaked into the comparison, "article" would show up
    # as resolved/new_or_worse and "verb_tense" 's rate would be skewed.
    await _session_with_debrief(
        client,
        db_session,
        headers,
        scenario="job_interview",
        cefr="A2",
        errors=[_err("article"), _err("article"), _err("article")],
        turns=10,
    )
    last = await _session_with_debrief(
        client,
        db_session,
        headers,
        scenario="job_interview",
        cefr="B1",
        errors=[],
        turns=10,
    )

    resp = await client.get("/me/proof/job_interview", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["baseline_session_id"] == first
    assert body["latest_session_id"] == last
    assert body["baseline_cefr"] == "A1"
    assert body["latest_cefr"] == "B1"
    # verb_tense: made at baseline, gone at latest -> resolved. article (middle
    # session only) must NOT appear anywhere — it was never baseline or latest.
    assert body["resolved"] == ["verb_tense"]
    assert body["improved"] == []
    assert body["new_or_worse"] == []


@pytest.mark.asyncio
async def test_proof_is_scoped_to_the_skill_and_user(client, db_session):
    headers = await _auth(client)
    # Two sessions but on DIFFERENT scenarios -> no proof for either.
    await _session_with_debrief(
        client, db_session, headers, scenario="restaurant", cefr="A2", errors=[]
    )
    await _session_with_debrief(
        client, db_session, headers, scenario="travel", cefr="B1", errors=[]
    )
    resp = await client.get("/me/proof/restaurant", headers=headers)
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_proof_requires_auth(client):
    resp = await client.get("/me/proof/job_interview")
    assert resp.status_code == 401, resp.text
