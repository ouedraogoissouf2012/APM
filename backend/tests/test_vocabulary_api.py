"""Integration tests for the vocabulary notebook API.

The debrief (fake engine) surfaces words; here we drive the notebook endpoints
directly by capturing through the service on a shared db session, then asserting
the HTTP list/patch behaviour.
"""

import pytest
from sqlalchemy import text

from app.features.debrief.domain import VocabularyWord
from app.features.vocabulary.repository import SqlAlchemyVocabularyRepository
from app.features.vocabulary.service import VocabularyService


async def _register(client):
    reg = await client.post("/auth/register", json={"email": "v@b.com", "password": "s3cret!pass"})
    token = reg.json()["access_token"]
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    return {"Authorization": f"Bearer {token}"}, me.json()["id"]


@pytest.mark.asyncio
async def test_list_empty_notebook(client):
    headers, _ = await _register(client)
    resp = await client.get("/vocabulary", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_and_mark_flow(client, db_session):
    headers, user_id = await _register(client)

    # Seed a couple of words as the debrief would.
    service = VocabularyService(SqlAlchemyVocabularyRepository(db_session))
    # session_id=None keeps the test free of a real session row; the FK path
    # (SET NULL on a real session) is exercised by the model/migration, not here.
    await service.capture(
        user_id,
        session_id=None,
        words=[
            VocabularyWord(
                word="deployment",
                phonetic="dɪˈplɔɪmənt",
                translation="déploiement",
                example="I handle deployments at work.",
            )
        ],
    )

    listed = await client.get("/vocabulary", headers=headers)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert len(body) == 1
    entry = body[0]
    assert entry["word"] == "deployment"
    assert entry["example"] == "I handle deployments at work."
    assert entry["status"] == "review"

    # Mark it known.
    marked = await client.patch(
        f"/vocabulary/{entry['id']}", headers=headers, json={"status": "known"}
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()["status"] == "known"


@pytest.mark.asyncio
async def test_patch_rejects_unknown_status(client, db_session):
    headers, user_id = await _register(client)
    service = VocabularyService(SqlAlchemyVocabularyRepository(db_session))
    await service.capture(user_id, None, [VocabularyWord(word="handle")])
    entry_id = (await client.get("/vocabulary", headers=headers)).json()[0]["id"]

    resp = await client.patch(
        f"/vocabulary/{entry_id}", headers=headers, json={"status": "mastered"}
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_cannot_mark_another_users_entry(client, db_session):
    headers_a, user_a = await _register(client)
    service = VocabularyService(SqlAlchemyVocabularyRepository(db_session))
    await service.capture(user_a, None, [VocabularyWord(word="handle")])
    entry_id = (await client.get("/vocabulary", headers=headers_a)).json()[0]["id"]

    # A different user must not be able to touch it.
    reg_b = await client.post(
        "/auth/register", json={"email": "b@b.com", "password": "s3cret!pass"}
    )
    headers_b = {"Authorization": f"Bearer {reg_b.json()['access_token']}"}
    resp = await client.patch(
        f"/vocabulary/{entry_id}", headers=headers_b, json={"status": "known"}
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_list_requires_auth(client):
    resp = await client.get("/vocabulary")
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_notebook_is_paginated_by_keyset(client, db_session):
    headers, user_id = await _register(client)
    service = VocabularyService(SqlAlchemyVocabularyRepository(db_session))
    for i in range(3):
        await service.capture(user_id, None, [VocabularyWord(word=f"word{i}")])

    page1 = await client.get("/vocabulary?limit=2", headers=headers)
    assert page1.status_code == 200, page1.text
    body1 = page1.json()
    assert [e["word"] for e in body1] == ["word2", "word1"]  # newest first

    last_id = body1[-1]["id"]
    page2 = await client.get(f"/vocabulary?limit=2&before_id={last_id}", headers=headers)
    assert page2.status_code == 200, page2.text
    assert [e["word"] for e in page2.json()] == ["word0"]


@pytest.mark.asyncio
async def test_list_rejects_oversized_limit(client):
    headers, _ = await _register(client)
    resp = await client.get("/vocabulary?limit=10000", headers=headers)
    assert resp.status_code == 422, resp.text  # le=MAX_PAGE_SIZE enforced at the boundary


@pytest.mark.asyncio
async def test_vocabulary_entries_has_session_id_index(db_session):
    """#358: session_id (FK SET NULL to sessions.id) must stay index-covered so a
    lookup/cascade by session never regresses to a sequential scan if the model
    is edited later. Checks the LIVE schema (provisioned by
    Base.metadata.create_all, same as CI), mirroring #288's review_items test."""
    result = await db_session.execute(
        text(
            "SELECT indexdef FROM pg_indexes WHERE tablename = 'vocabulary_entries'"
            " AND indexname = 'ix_vocabulary_entries_session_id'"
        )
    )
    indexdef = result.scalar_one_or_none()
    assert indexdef is not None, "session_id index is missing"
    assert indexdef.endswith("(session_id)"), indexdef
