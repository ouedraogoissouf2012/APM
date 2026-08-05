"""Integration tests for GET /me/proof/{skill} (#126)."""

import pytest

from app.features.debrief.repository import SqlAlchemyDebriefRepository


async def _auth(client):
    reg = await client.post("/auth/register", json={"email": "pf@b.com", "password": "s3cret!pass"})
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


async def _session_with_debrief(client, db_session, headers, *, scenario, cefr, errors):
    start = await client.post(
        "/sessions/start",
        headers=headers,
        json={"mode": "scenario", "scenario_id": scenario},
    )
    session_id = start.json()["session_id"]
    await client.post(f"/sessions/{session_id}/end", headers=headers)
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
