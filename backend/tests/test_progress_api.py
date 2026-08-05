"""Integration tests for GET /me/progress.

Sessions + debriefs are seeded directly on the shared db session, then the
endpoint is asserted to aggregate the CEFR trend and recurring errors (replacing
the old client-side one-debrief-per-session loop).
"""

import pytest

from app.features.debrief.repository import SqlAlchemyDebriefRepository


async def _auth(client):
    reg = await client.post("/auth/register", json={"email": "pg@b.com", "password": "s3cret!pass"})
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


async def _completed_session(client, db_session, headers, *, cefr, errors):
    """Start a real session (owned by the auth'd user) and attach a debrief."""
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]
    await client.post(f"/sessions/{session_id}/end", headers=headers)
    await SqlAlchemyDebriefRepository(db_session).save(session_id, cefr, "summary", errors)
    return session_id


def _err(error_type, correction):
    return {"error_type": error_type, "correction": correction, "original": "x", "rule": "r"}


@pytest.mark.asyncio
async def test_empty_progress(client):
    headers = await _auth(client)
    resp = await client.get("/me/progress", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"cefr_trend": [], "recurring_errors": []}


@pytest.mark.asyncio
async def test_progress_aggregates_trend_and_recurring_errors(client, db_session):
    headers = await _auth(client)

    await _completed_session(
        client, db_session, headers, cefr="A2", errors=[_err("verb_tense", "I went")]
    )
    await _completed_session(
        client,
        db_session,
        headers,
        cefr="B1",
        errors=[_err("verb_tense", "she runs"), _err("article", "a cat")],
    )

    resp = await client.get("/me/progress", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Trend has both sessions, oldest first.
    assert [p["level"] for p in body["cefr_trend"]] == ["A2", "B1"]

    # verb_tense appears twice, article once → verb_tense ranks first.
    recurring = body["recurring_errors"]
    assert recurring[0]["error_type"] == "verb_tense"
    assert recurring[0]["count"] == 2
    assert {e["error_type"] for e in recurring} == {"verb_tense", "article"}


@pytest.mark.asyncio
async def test_progress_only_sees_own_sessions(client, db_session):
    headers_a = await _auth(client)
    await _completed_session(
        client, db_session, headers_a, cefr="B2", errors=[_err("article", "the sun")]
    )

    reg_b = await client.post(
        "/auth/register", json={"email": "pg-b@b.com", "password": "s3cret!pass"}
    )
    headers_b = {"Authorization": f"Bearer {reg_b.json()['access_token']}"}

    resp = await client.get("/me/progress", headers=headers_b)
    assert resp.json() == {"cefr_trend": [], "recurring_errors": []}


@pytest.mark.asyncio
async def test_progress_requires_auth(client):
    resp = await client.get("/me/progress")
    assert resp.status_code == 401, resp.text
