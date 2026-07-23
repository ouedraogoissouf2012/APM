import pytest

from app.domain.exceptions import ConflictError, NotFoundError
from app.features.auth.models import User
from app.features.conversation.correction import TurnCorrection, TurnCorrector
from app.features.conversation.turn_service import (
    ConversationTurnService,
    CorrectionReady,
    ReplyChunk,
)


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


class _FakeProfiles:
    def __init__(self, interests=None, goal=None, memory_summary="") -> None:
        self._interests = interests
        self._goal = goal
        self._memory_summary = memory_summary

    async def get_by_user_id(self, user_id):
        if self._interests is None and self._goal is None and not self._memory_summary:
            return None

        class _P:
            interests = self._interests or []
            goal = self._goal
            memory_summary = self._memory_summary

        return _P()


class _CannedLlm:
    def __init__(self, reply: str = "Nice!") -> None:
        self._reply = reply
        self.seen_history = None
        self.seen_system = None

    async def complete(self, system_prompt, history):
        self.seen_system = system_prompt
        self.seen_history = history
        return self._reply


class _StreamingLlm:
    """Yields the reply as pre-split sentence chunks."""

    def __init__(self, chunks) -> None:
        self._chunks = chunks
        self.seen_history = None

    async def complete(self, system_prompt, history):  # pragma: no cover - unused
        return " ".join(self._chunks)

    async def stream_complete(self, system_prompt, history):
        self.seen_history = history
        for chunk in self._chunks:
            yield chunk


def _user() -> User:
    u = User(email="c@b.com", hashed_password="x", native_language="fr")
    u.id = 7
    u.cefr_level = "A2"
    return u


def _service(sessions, transcripts, llm, profiles=None, corrector=None):
    return ConversationTurnService(
        sessions, transcripts, profiles or _FakeProfiles(), llm, corrector=corrector
    )


class _CannedCorrector:
    """Stands in for TurnCorrector; returns a fixed correction (or None)."""

    def __init__(self, correction) -> None:
        self._correction = correction

    async def correct(self, text, cefr_level, native_language):
        return self._correction


@pytest.mark.asyncio
async def test_take_turn_appends_user_and_assistant_and_persists():
    transcripts = _FakeTranscripts()
    service = _service(_FakeSessions(owner_id=7), transcripts, _CannedLlm("Hi there!"))

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
    service = _service(_FakeSessions(owner_id=7), _FakeTranscripts(prior), llm)

    await service.take_turn(1, _user(), "how are you")

    assert [m.content for m in llm.seen_history] == ["hi", "hello", "how are you"]


@pytest.mark.asyncio
async def test_take_turn_personalizes_prompt_from_profile():
    llm = _CannedLlm()
    service = _service(
        _FakeSessions(owner_id=7),
        _FakeTranscripts(),
        llm,
        profiles=_FakeProfiles(interests=["football", "cooking"], goal="travel to the UK"),
    )

    await service.take_turn(1, _user(), "hello")

    assert "football" in llm.seen_system
    assert "cooking" in llm.seen_system
    assert "travel to the UK" in llm.seen_system


@pytest.mark.asyncio
async def test_take_turn_injects_learner_memory_into_prompt():
    llm = _CannedLlm()
    service = _service(
        _FakeSessions(owner_id=7),
        _FakeTranscripts(),
        llm,
        profiles=_FakeProfiles(memory_summary="Last session: user struggled with past tense."),
    )

    await service.take_turn(1, _user(), "hello")

    assert "past tense" in llm.seen_system


@pytest.mark.asyncio
async def test_stream_turn_yields_sentences_then_persists_full_reply():
    transcripts = _FakeTranscripts()
    llm = _StreamingLlm(["Hi there.", "How are you?"])
    service = _service(_FakeSessions(owner_id=7), transcripts, llm)

    events = [c async for c in service.stream_turn(1, _user(), "hello")]

    # The client receives each sentence as it is produced (no corrector here).
    assert [e.text for e in events if isinstance(e, ReplyChunk)] == [
        "Hi there.",
        "How are you?",
    ]
    assert not any(isinstance(e, CorrectionReady) for e in events)
    # The full reply is persisted once, joined, alongside the user turn.
    assert transcripts.saved == (
        1,
        [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "Hi there. How are you?"},
        ],
    )


@pytest.mark.asyncio
async def test_stream_turn_emits_a_correction_after_the_reply():
    correction = TurnCorrection(
        original="i is happy", correction="I am happy", rule="Use 'am' with 'I'."
    )
    service = _service(
        _FakeSessions(owner_id=7),
        _FakeTranscripts(),
        _StreamingLlm(["Nice."]),
        corrector=_CannedCorrector(correction),
    )

    events = [c async for c in service.stream_turn(1, _user(), "i is happy")]

    # Reply chunk(s) first, correction last (never interrupting the flow).
    assert isinstance(events[0], ReplyChunk)
    assert isinstance(events[-1], CorrectionReady)
    assert events[-1].correction == correction


@pytest.mark.asyncio
async def test_stream_turn_emits_no_correction_event_when_there_is_no_mistake():
    service = _service(
        _FakeSessions(owner_id=7),
        _FakeTranscripts(),
        _StreamingLlm(["Nice."]),
        corrector=_CannedCorrector(None),
    )

    events = [c async for c in service.stream_turn(1, _user(), "I am happy")]

    assert all(isinstance(e, ReplyChunk) for e in events)


@pytest.mark.asyncio
async def test_stream_turn_with_real_corrector_uses_the_llm_json():
    # Wire a real TurnCorrector over a canned JSON LLM (end-to-end of the unit).
    class _JsonLlm(_StreamingLlm):
        async def complete(self, system_prompt, history):
            return (
                '{"has_error": true, "original": "i is happy", '
                '"correction": "I am happy", "rule": "Use am with I."}'
            )

    llm = _JsonLlm(["Great."])
    service = _service(
        _FakeSessions(owner_id=7),
        _FakeTranscripts(),
        llm,
        corrector=TurnCorrector(llm),
    )

    events = [c async for c in service.stream_turn(1, _user(), "i is happy")]
    corrections = [e for e in events if isinstance(e, CorrectionReady)]
    assert len(corrections) == 1
    assert corrections[0].correction.correction == "I am happy"


@pytest.mark.asyncio
async def test_stream_turn_includes_prior_history():
    prior = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    llm = _StreamingLlm(["Sure."])
    service = _service(_FakeSessions(owner_id=7), _FakeTranscripts(prior), llm)

    _ = [c async for c in service.stream_turn(1, _user(), "and you?")]

    assert [m.content for m in llm.seen_history] == ["hi", "hello", "and you?"]


@pytest.mark.asyncio
async def test_stream_turn_rejects_ended_session():
    llm = _StreamingLlm(["x"])
    service = _service(_FakeSessions(owner_id=7, ended=True), _FakeTranscripts(), llm)
    with pytest.raises(ConflictError):
        _ = [c async for c in service.stream_turn(1, _user(), "hello")]


@pytest.mark.asyncio
async def test_take_turn_rejects_session_not_owned():
    service = _service(_FakeSessions(owner_id=999), _FakeTranscripts(), _CannedLlm())
    with pytest.raises(NotFoundError):
        await service.take_turn(1, _user(), "hello")


@pytest.mark.asyncio
async def test_take_turn_rejects_ended_session():
    service = _service(_FakeSessions(owner_id=7, ended=True), _FakeTranscripts(), _CannedLlm())
    with pytest.raises(ConflictError):
        await service.take_turn(1, _user(), "hello")
