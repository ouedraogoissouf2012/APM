import pytest

from app.domain.exceptions import ConflictError, NotFoundError
from app.features.auth.models import User
from app.features.conversation.turn_service import ConversationTurnService


class _FakeSessions:
    def __init__(self, owner_id: int | None, ended: bool = False) -> None:
        self._owner_id = owner_id
        self._ended = ended

    async def get(self, session_id):
        if self._owner_id is None:
            return None

        class _S:
            user_id = self._owner_id
            scenario_id = None
            ended_at = "2026-01-01" if self._ended else None

        return _S()


class _FakeTranscripts:
    def __init__(self, existing_turns=None) -> None:
        self.saved = None
        self._existing_turns = existing_turns

    async def get_by_session(self, session_id):
        if self._existing_turns is None:
            return None

        class _T:
            turns = self._existing_turns

        return _T()

    async def save(self, session_id, turns):
        self.saved = (session_id, turns)

        class _Saved:
            pass

        s = _Saved()
        s.turns = turns
        return s


class _CannedLlm:
    def __init__(self, reply: str = "Nice!") -> None:
        self._reply = reply
        self.seen_history = None

    async def complete(self, system_prompt, history):
        self.seen_history = history
        return self._reply


def _user() -> User:
    u = User(email="c@b.com", hashed_password="x", native_language="fr")
    u.id = 7
    u.cefr_level = "A2"
    return u


@pytest.mark.asyncio
async def test_take_turn_appends_user_and_assistant_and_persists():
    transcripts = _FakeTranscripts()
    service = ConversationTurnService(
        _FakeSessions(owner_id=7), transcripts, _CannedLlm("Hi there!")
    )

    result = await service.take_turn(1, _user(), "hello")

    assert result.reply == "Hi there!"
    assert result.turns == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    assert transcripts.saved == (1, result.turns)


@pytest.mark.asyncio
async def test_take_turn_includes_prior_history_in_llm_call():
    prior = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    llm = _CannedLlm()
    service = ConversationTurnService(_FakeSessions(owner_id=7), _FakeTranscripts(prior), llm)

    await service.take_turn(1, _user(), "how are you")

    # system prompt + 2 prior + new user message all reach the LLM as history.
    assert [m.content for m in llm.seen_history] == ["hi", "hello", "how are you"]


@pytest.mark.asyncio
async def test_take_turn_rejects_session_not_owned():
    service = ConversationTurnService(_FakeSessions(owner_id=999), _FakeTranscripts(), _CannedLlm())
    with pytest.raises(NotFoundError):
        await service.take_turn(1, _user(), "hello")


@pytest.mark.asyncio
async def test_take_turn_rejects_ended_session():
    service = ConversationTurnService(
        _FakeSessions(owner_id=7, ended=True), _FakeTranscripts(), _CannedLlm()
    )
    with pytest.raises(ConflictError):
        await service.take_turn(1, _user(), "hello")
