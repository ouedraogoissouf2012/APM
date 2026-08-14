"""Repository-level tests for SqlAlchemyVoiceDataSource's export streaming
(#365): each category must be fetched off a server-side cursor
(AsyncSession.stream/stream_scalars), never execute()/scalars(), which buffer
the whole result set before returning a single row."""

from datetime import UTC, datetime

import pytest

from app.core.llm.messages import ROLE_ASSISTANT, ROLE_USER
from app.features.auth.models import User
from app.features.conversation.repository import SqlAlchemyTranscriptRepository
from app.features.sessions.models import ConversationSession
from app.features.voice_data.repository import SqlAlchemyVoiceDataSource


async def _user(db_session) -> User:
    user = User(email="voicedatarepo@b.com", hashed_password="x", native_language="fr")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.mark.asyncio
async def test_stream_methods_use_a_server_side_cursor_not_a_buffered_query(
    db_session, monkeypatch
):
    user = await _user(db_session)
    real_execute = db_session.execute
    real_scalars = db_session.scalars
    execute_calls = []
    scalars_calls = []

    async def _spy_execute(*args, **kwargs):
        execute_calls.append(args)
        return await real_execute(*args, **kwargs)

    async def _spy_scalars(*args, **kwargs):
        scalars_calls.append(args)
        return await real_scalars(*args, **kwargs)

    monkeypatch.setattr(db_session, "execute", _spy_execute)
    monkeypatch.setattr(db_session, "scalars", _spy_scalars)

    source = SqlAlchemyVoiceDataSource(db_session)
    async for _ in source.stream_utterances(user.id):
        pass
    async for _ in source.stream_vocabulary(user.id):
        pass
    async for _ in source.stream_debriefs(user.id):
        pass
    async for _ in source.stream_review_items(user.id):
        pass

    assert execute_calls == [], "export must stream via session.stream(), not execute()"
    assert scalars_calls == [], "export must stream via session.stream_scalars(), not scalars()"


@pytest.mark.asyncio
async def test_list_returning_methods_still_return_every_row(db_session):
    """The Protocol-required list-returning wrappers (utterances/vocabulary/
    debriefs/review_items, still used by VoiceDataService/erasure) must drain
    the stream completely — no row silently dropped by the rewrite."""
    user = await _user(db_session)
    session = ConversationSession(user_id=user.id, mode="free", started_at=datetime.now(UTC))
    db_session.add(session)
    await db_session.flush()
    turns = []
    for i in range(7):
        turns.append({"role": ROLE_ASSISTANT, "content": "?"})
        turns.append({"role": ROLE_USER, "content": f"turn {i}"})
    await SqlAlchemyTranscriptRepository(db_session).save(session.id, turns)
    await db_session.commit()

    source = SqlAlchemyVoiceDataSource(db_session)
    utterances = await source.utterances(user.id)

    assert len(utterances) == 7
    assert [u["text"] for u in utterances] == [f"turn {i}" for i in range(7)]
