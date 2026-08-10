import pytest

from app.domain.exceptions import ConflictError, LlmProviderError, NotFoundError
from app.features.auth.models import User
from app.features.conversation.correction import TurnCorrection, TurnCorrector
from app.features.conversation.turn_service import (
    AudioChunk,
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
            mission_id = None
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
    def __init__(
        self, interests=None, goal=None, memory_summary="", correction_intensity="gentle"
    ) -> None:
        self._interests = interests
        self._goal = goal
        self._memory_summary = memory_summary
        self._correction_intensity = correction_intensity

    async def get_by_user_id(self, user_id):
        if self._interests is None and self._goal is None and not self._memory_summary:
            return None

        class _P:
            interests = self._interests or []
            goal = self._goal
            memory_summary = self._memory_summary
            correction_intensity = self._correction_intensity

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


class _PartialThenFailingLlm:
    """Streams a few sentences, then the provider dies mid-reply."""

    def __init__(self, chunks) -> None:
        self._chunks = chunks

    async def complete(self, system_prompt, history):  # pragma: no cover - unused
        raise LlmProviderError("LLM provider failed")

    async def stream_complete(self, system_prompt, history):
        for chunk in self._chunks:
            yield chunk
        raise LlmProviderError("LLM provider failed")


def _user() -> User:
    u = User(email="c@b.com", hashed_password="x", native_language="fr")
    u.id = 7
    u.cefr_level = "A2"
    return u


def _service(sessions, transcripts, llm, profiles=None, corrector=None, tts=None, meter=None):
    return ConversationTurnService(
        sessions,
        transcripts,
        profiles or _FakeProfiles(),
        llm,
        corrector=corrector,
        tts=tts,
        meter=meter,
    )


class _FakeTts:
    """Returns deterministic 'audio' bytes so the stream is exercisable."""

    async def synthesize(self, text: str) -> bytes:
        return f"audio::{text}".encode()


class _CannedCorrector:
    """Stands in for TurnCorrector; returns a fixed correction (or None) and
    records the intensity it was called with (#114)."""

    def __init__(self, correction) -> None:
        self._correction = correction
        self.seen_intensity = None

    async def correct(self, text, cefr_level, native_language, intensity="gentle"):
        self.seen_intensity = intensity
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
async def test_take_turn_meters_the_quota_once_per_turn():
    # #119: every turn meters the quota, so an abandoned session (no /end) is still
    # bounded. The meter is called with (session_id, user_id).
    calls: list[tuple[int, int]] = []

    async def _meter(session_id: int, user_id: int) -> None:
        calls.append((session_id, user_id))

    service = _service(_FakeSessions(owner_id=7), _FakeTranscripts(), _CannedLlm(), meter=_meter)
    await service.take_turn(1, _user(), "hello")
    assert calls == [(1, 7)]


@pytest.mark.asyncio
async def test_take_turn_survives_a_metering_failure():
    # Metering is best-effort: if it raises, the turn still succeeds.
    async def _boom(session_id: int, user_id: int) -> None:
        raise RuntimeError("db down")

    service = _service(
        _FakeSessions(owner_id=7), _FakeTranscripts(), _CannedLlm("Hi!"), meter=_boom
    )
    result = await service.take_turn(1, _user(), "hello")
    assert result.reply == "Hi!"  # the turn is unaffected


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
async def test_take_turn_windows_history_to_the_last_n_messages():
    # #224: a long conversation must NOT replay its entire transcript to the LLM
    # every turn (unbounded cost + latency). Only the last N messages go to the
    # model; the full transcript is still persisted and the profile memory carries
    # the older context.
    prior = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"}
        for i in range(10)  # m0..m9
    ]
    llm = _CannedLlm()
    service = ConversationTurnService(
        _FakeSessions(owner_id=7),
        _FakeTranscripts(prior),
        _FakeProfiles(),
        llm,
        history_max_messages=4,
    )

    result = await service.take_turn(1, _user(), "now")

    # Only the last 4 prior messages + the new user turn reach the LLM...
    assert [m.content for m in llm.seen_history] == ["m6", "m7", "m8", "m9", "now"]
    # ...but the FULL transcript is still persisted (all 10 + this exchange).
    assert len(result.turns) == 12
    assert result.turns[0]["content"] == "m0"


@pytest.mark.asyncio
async def test_history_window_of_zero_means_unlimited():
    prior = [{"role": "user", "content": f"m{i}"} for i in range(6)]
    llm = _CannedLlm()
    service = ConversationTurnService(
        _FakeSessions(owner_id=7),
        _FakeTranscripts(prior),
        _FakeProfiles(),
        llm,
        history_max_messages=0,  # 0 = no window
    )

    await service.take_turn(1, _user(), "now")

    assert [m.content for m in llm.seen_history] == ["m0", "m1", "m2", "m3", "m4", "m5", "now"]


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
async def test_stream_turn_speaks_each_sentence_as_it_is_produced():
    # Latency fix: audio is synthesized PER SENTENCE and emitted while the reply is
    # still being generated, so the voice starts after the first sentence (~1-2 s)
    # instead of after the whole reply + its synthesis (~5 s). The client plays the
    # clips sequentially (await playClip), so they don't cut each other off.
    import base64

    service = _service(
        _FakeSessions(owner_id=7),
        _FakeTranscripts(),
        _StreamingLlm(["Hi there.", "How are you?"]),
        tts=_FakeTts(),
    )

    events = [c async for c in service.stream_turn(1, _user(), "hello")]

    # One audio clip per sentence, and the first audio arrives before the whole
    # text is done (so the voice starts early).
    audios = [e for e in events if isinstance(e, AudioChunk)]
    assert len(audios) == 2
    clips = [base64.b64decode(a.audio_b64) for a in audios]
    assert clips == [b"audio::Hi there.", b"audio::How are you?"]
    # The FIRST audio clip is emitted before the SECOND sentence's text — proving
    # the voice can start speaking sentence 1 while sentence 2 is still streaming.
    kinds = [type(e).__name__ for e in events]
    assert kinds.index("AudioChunk") < len(kinds) - 1
    assert audios[0].mime == "audio/mpeg"


@pytest.mark.asyncio
async def test_stream_turn_emits_no_audio_when_no_tts():
    service = _service(_FakeSessions(owner_id=7), _FakeTranscripts(), _StreamingLlm(["Hi."]))
    events = [c async for c in service.stream_turn(1, _user(), "hello")]
    assert not any(isinstance(e, AudioChunk) for e in events)


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
async def test_stream_turn_passes_profile_correction_intensity_to_the_corrector():
    # #114: the learner's stored intensity must reach the corrector, not a default.
    corrector = _CannedCorrector(None)
    service = _service(
        _FakeSessions(owner_id=7),
        _FakeTranscripts(),
        _StreamingLlm(["Nice."]),
        corrector=corrector,
        profiles=_FakeProfiles(memory_summary="x", correction_intensity="detailed"),
    )

    _ = [c async for c in service.stream_turn(1, _user(), "i is happy")]
    assert corrector.seen_intensity == "detailed"


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
async def test_stream_turn_persists_partial_reply_when_stream_fails_midway():
    # The provider dies after two sentences the learner has already heard. The
    # exchange must NOT vanish from the transcript, or the next turn's history
    # (and the end-of-session debrief) silently loses what was actually said.
    transcripts = _FakeTranscripts()
    llm = _PartialThenFailingLlm(["Hi there.", "How are"])
    service = _service(_FakeSessions(owner_id=7), transcripts, llm)

    seen: list[str] = []
    with pytest.raises(LlmProviderError):
        async for event in service.stream_turn(1, _user(), "hello"):
            if isinstance(event, ReplyChunk):
                seen.append(event.text)

    assert seen == ["Hi there.", "How are"]
    assert transcripts.saved == (
        1,
        [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "Hi there. How are"},
        ],
    )


@pytest.mark.asyncio
async def test_stream_turn_persists_nothing_when_it_fails_before_any_output():
    # Nothing was produced, so there is nothing to persist — consistent with
    # take_turn, which saves nothing when the reply itself fails.
    transcripts = _FakeTranscripts()
    llm = _PartialThenFailingLlm([])
    service = _service(_FakeSessions(owner_id=7), transcripts, llm)

    with pytest.raises(LlmProviderError):
        async for _event in service.stream_turn(1, _user(), "hello"):
            pass

    assert transcripts.saved is None


@pytest.mark.asyncio
async def test_stream_prepared_finalises_before_the_correction_frame():
    # #261: on_persisted (which caches the idempotency key) MUST run right after the
    # turn is persisted and BEFORE the correction frame is yielded — otherwise a
    # client disconnect on that frame leaves the turn charged but the key
    # un-completed, and a retry double-charges.
    correction = TurnCorrection(
        original="i is happy", correction="I am happy", rule="Use 'am' with 'I'."
    )
    service = _service(
        _FakeSessions(owner_id=7),
        _FakeTranscripts(),
        _StreamingLlm(["Nice."]),
        corrector=_CannedCorrector(correction),
    )
    order: list[str] = []

    async def on_persisted(reply: str) -> None:
        order.append(f"persisted:{reply}")

    prepared = await service.prepare_turn(1, _user(), "i is happy")
    async for event in service.stream_prepared(prepared, on_persisted):
        if isinstance(event, CorrectionReady):
            order.append("correction")

    assert order == ["persisted:Nice.", "correction"]  # finalise BEFORE the correction


@pytest.mark.asyncio
async def test_stream_prepared_finalises_the_partial_on_a_mid_stream_failure():
    # A partial reply is persisted + metered before the failure, so on_persisted must
    # fire on it too — the streaming route then caches the key on the partial instead
    # of releasing it, so a retry replays the partial rather than double-charging (#261).
    service = _service(
        _FakeSessions(owner_id=7),
        _FakeTranscripts(),
        _PartialThenFailingLlm(["Hi there.", "How are"]),
    )
    persisted: list[str] = []

    async def on_persisted(reply: str) -> None:
        persisted.append(reply)

    prepared = await service.prepare_turn(1, _user(), "hello")
    with pytest.raises(LlmProviderError):
        async for _event in service.stream_prepared(prepared, on_persisted):
            pass

    assert persisted == ["Hi there. How are"]  # finalised on the persisted partial


@pytest.mark.asyncio
async def test_stream_prepared_does_not_finalise_when_nothing_is_produced():
    # Nothing was persisted, so on_persisted must NOT fire — the streaming route then
    # RELEASES the claim so a retry can cleanly re-run (#261).
    service = _service(_FakeSessions(owner_id=7), _FakeTranscripts(), _PartialThenFailingLlm([]))
    persisted: list[str] = []

    async def on_persisted(reply: str) -> None:
        persisted.append(reply)

    prepared = await service.prepare_turn(1, _user(), "hello")
    with pytest.raises(LlmProviderError):
        async for _event in service.stream_prepared(prepared, on_persisted):
            pass

    assert persisted == []  # nothing persisted -> nothing finalised -> route releases


@pytest.mark.asyncio
async def test_stream_turn_completes_when_the_final_persist_fails_after_full_delivery(caplog):
    # #238: the WHOLE reply was already streamed to the client. If persisting the
    # transcript then fails, that must NOT surface as an `error` event — the learner
    # already has the complete reply. The stream ends normally (every chunk
    # delivered, nothing raised) and the transcript desync is logged for ops.
    class _FailingOnSaveTranscripts:
        async def get_by_session(self, session_id):
            return None

        async def save(self, session_id, turns):
            raise RuntimeError("db commit failed")

    service = _service(
        _FakeSessions(owner_id=7),
        _FailingOnSaveTranscripts(),
        _StreamingLlm(["Hi there.", "How are you?"]),
    )

    with caplog.at_level("ERROR"):
        events = [c async for c in service.stream_turn(1, _user(), "hello")]

    # Every reply chunk was delivered and NO exception propagated (no `error`).
    assert [e.text for e in events if isinstance(e, ReplyChunk)] == [
        "Hi there.",
        "How are you?",
    ]
    assert "persist failed" in caplog.text  # the desync is logged, not shown as an error


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
