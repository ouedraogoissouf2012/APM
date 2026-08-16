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

    async def save(self, session_id, turns, *, commit=True):
        self.saved = (session_id, turns)

        class _Saved:
            pass

        s = _Saved()
        s.turns = turns
        return s

    async def commit(self):
        return None


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


class _OrderRecordingLlm:
    """Records the shared event log at the moment the LLM runs, so a test can
    assert the DB connection was released BEFORE the LLM I/O (#399)."""

    def __init__(self, events: list[str], reply: str = "Nice!") -> None:
        self._events = events
        self._reply = reply

    async def complete(self, system_prompt, history):
        self._events.append("llm")
        return self._reply

    async def stream_complete(self, system_prompt, history):
        self._events.append("llm")
        for chunk in self._reply.split(". "):
            yield chunk


class _RecordingTranscripts:
    """A transcript repo that logs a tag when it saves — used to tell the FRESH
    persistence scope's repo apart from the request-scoped one (#399)."""

    def __init__(self, events: list[str], tag: str) -> None:
        self._events = events
        self._tag = tag
        self.saved = None

    async def get_by_session(self, session_id):
        return None

    async def save(self, session_id, turns, *, commit=True):
        self._events.append(f"save:{self._tag}")
        self.saved = (session_id, turns)

        class _Saved:
            pass

        s = _Saved()
        s.turns = turns
        return s

    async def commit(self):
        return None


def _io_boundary(events: list[str]):
    async def _release() -> None:
        events.append("release")

    return _release


def _fresh_scope(fresh_transcripts, events: list[str], meter=None):
    from contextlib import asynccontextmanager

    from app.features.conversation.turn_service import TurnPersistence

    @asynccontextmanager
    async def _factory():
        events.append("scope:open")
        try:
            yield TurnPersistence(fresh_transcripts, meter)
        finally:
            events.append("scope:close")

    return _factory


@pytest.mark.asyncio
async def test_take_turn_releases_connection_before_llm_then_persists_on_fresh_scope():
    # #399: the request connection is released at the I/O boundary (BEFORE the LLM),
    # and the terminal write goes to the FRESH persistence scope, never the
    # request-scoped transcript repo held during the reads.
    events: list[str] = []
    request_transcripts = _RecordingTranscripts(events, "request")
    fresh_transcripts = _RecordingTranscripts(events, "fresh")
    service = ConversationTurnService(
        _FakeSessions(owner_id=7),
        request_transcripts,
        _FakeProfiles(),
        _OrderRecordingLlm(events, "Hi!"),
        io_boundary=_io_boundary(events),
        persistence=_fresh_scope(fresh_transcripts, events),
    )

    await service.take_turn(1, _user(), "hello")

    # Connection released BEFORE the LLM; fresh scope opened AFTER it; the save
    # lands on the fresh repo (not the request one held during the reads).
    assert events == ["release", "llm", "scope:open", "save:fresh", "scope:close"]
    assert request_transcripts.saved is None
    assert fresh_transcripts.saved is not None


@pytest.mark.asyncio
async def test_take_turn_meters_on_the_fresh_scope_not_the_request_meter():
    # #399: the meter must run on the FRESH connection too, so the whole terminal
    # write (transcript + quota) holds one short-lived connection, not the request's.
    events: list[str] = []
    fresh_calls: list[tuple[int, int]] = []
    request_calls: list[tuple[int, int]] = []

    async def _fresh_meter(session_id: int, user_id: int) -> None:
        fresh_calls.append((session_id, user_id))

    async def _request_meter(session_id: int, user_id: int) -> None:  # pragma: no cover
        request_calls.append((session_id, user_id))

    service = ConversationTurnService(
        _FakeSessions(owner_id=7),
        _FakeTranscripts(),
        _FakeProfiles(),
        _CannedLlm(),
        meter=_request_meter,  # would be used only WITHOUT a fresh scope
        io_boundary=_io_boundary(events),
        persistence=_fresh_scope(
            _RecordingTranscripts(events, "fresh"), events, meter=_fresh_meter
        ),
    )

    await service.take_turn(1, _user(), "hello")

    assert fresh_calls == [(1, 7)]
    assert request_calls == []  # the request-scoped meter is NOT used


@pytest.mark.asyncio
async def test_take_turn_swallows_fresh_meter_failure_and_logs_it(caplog):
    # #418: a broken fresh-session meter must not fail the turn (transcript is
    # already saved) but the best-effort failure must stay observable.
    events: list[str] = []
    fresh_transcripts = _RecordingTranscripts(events, "fresh")

    async def _exploding_meter(session_id: int, user_id: int) -> None:
        raise RuntimeError("fresh meter exploded")

    service = ConversationTurnService(
        _FakeSessions(owner_id=7),
        _FakeTranscripts(),
        _FakeProfiles(),
        _CannedLlm(),
        io_boundary=_io_boundary(events),
        persistence=_fresh_scope(fresh_transcripts, events, meter=_exploding_meter),
    )

    result = await service.take_turn(1, _user(), "hello")

    assert result.reply  # turn still succeeded
    assert fresh_transcripts.saved is not None
    assert any("Per-turn quota metering failed" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_stream_turn_releases_connection_before_llm_then_persists_on_fresh_scope():
    # #399, streaming path: same guarantee as take_turn — release, stream the LLM,
    # then persist the full reply on a fresh scope.
    events: list[str] = []
    fresh_transcripts = _RecordingTranscripts(events, "fresh")
    service = ConversationTurnService(
        _FakeSessions(owner_id=7),
        _RecordingTranscripts(events, "request"),
        _FakeProfiles(),
        _OrderRecordingLlm(events, "Hi there. How are you?"),
        io_boundary=_io_boundary(events),
        persistence=_fresh_scope(fresh_transcripts, events),
    )

    _ = [c async for c in service.stream_turn(1, _user(), "hello")]

    assert events[0] == "release"  # connection freed before anything streams
    assert events.index("llm") < events.index("scope:open")  # LLM before the fresh scope
    assert "save:fresh" in events and "save:request" not in events


@pytest.mark.asyncio
async def test_stream_turn_persists_partial_on_fresh_scope_after_release():
    # #399: even the mid-stream-failure partial persist must go to the fresh scope,
    # after the connection was released — not the request repo.
    events: list[str] = []
    fresh_transcripts = _RecordingTranscripts(events, "fresh")
    service = ConversationTurnService(
        _FakeSessions(owner_id=7),
        _RecordingTranscripts(events, "request"),
        _FakeProfiles(),
        _PartialThenFailingLlm(["Hi there.", "How are"]),
        io_boundary=_io_boundary(events),
        persistence=_fresh_scope(fresh_transcripts, events),
    )

    with pytest.raises(LlmProviderError):
        async for _event in service.stream_turn(1, _user(), "hello"):
            pass

    assert events[0] == "release"
    assert "save:fresh" in events and "save:request" not in events
    assert fresh_transcripts.saved[1][-1]["content"] == "Hi there. How are"


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
async def test_persisted_transcript_is_capped_to_transcript_max_messages():
    # #364: the PERSISTED transcript (not just the LLM history window) must be
    # bounded too, or a long/abusive paid-tier session grows it (and the cost of
    # rewriting it every turn) without limit. The newest messages are always kept;
    # the oldest are dropped once the cap is exceeded.
    prior = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"}
        for i in range(6)  # m0..m5
    ]
    llm = _CannedLlm()
    service = ConversationTurnService(
        _FakeSessions(owner_id=7),
        _FakeTranscripts(prior),
        _FakeProfiles(),
        llm,
        transcript_max_messages=6,
    )

    result = await service.take_turn(1, _user(), "now")

    # 6 prior + 2 new = 8, capped to the most recent 6 -> the oldest 2 (m0, m1) drop.
    assert len(result.turns) == 6
    assert [t["content"] for t in result.turns] == ["m2", "m3", "m4", "m5", "now", "Nice!"]


@pytest.mark.asyncio
async def test_transcript_cap_of_zero_means_unlimited():
    prior = [{"role": "user", "content": f"m{i}"} for i in range(50)]
    llm = _CannedLlm()
    service = ConversationTurnService(
        _FakeSessions(owner_id=7),
        _FakeTranscripts(prior),
        _FakeProfiles(),
        llm,
        transcript_max_messages=0,  # 0 = no cap
    )

    result = await service.take_turn(1, _user(), "now")

    assert len(result.turns) == 52


class _StatefulFakeTranscripts:
    """Unlike _FakeTranscripts (a fixed snapshot), this actually persists what
    save() writes so a test can replay a MULTI-turn session and observe how the
    stored transcript's size evolves turn over turn — the shape #364's fix is
    about."""

    def __init__(self) -> None:
        self._by_session: dict[int, list[dict]] = {}
        self.save_sizes: list[int] = []

    async def get_by_session(self, session_id):
        turns = self._by_session.get(session_id)
        if turns is None:
            return None

        class _T:
            pass

        t = _T()
        t.turns = turns
        return t

    async def save(self, session_id, turns, *, commit=True):
        self._by_session[session_id] = turns
        self.save_sizes.append(len(turns))

    async def commit(self):
        return None


@pytest.mark.asyncio
async def test_long_session_persisted_size_plateaus_at_the_cap_instead_of_growing_forever():
    # #364: the concrete before/after this issue is about. BEFORE the fix, the
    # persisted array grows by 2 every turn forever (2, 4, 6, 8, ... 40 over 20
    # turns) — an unbounded, "non borne" cost in a long paid-tier session, and
    # what gets rewritten in full on every single turn. AFTER the fix, it grows
    # the same way only until the cap, then plateaus — the per-turn write cost
    # becomes CONSTANT regardless of how long the session runs.
    transcripts = _StatefulFakeTranscripts()
    service = ConversationTurnService(
        _FakeSessions(owner_id=7),
        transcripts,
        _FakeProfiles(),
        _CannedLlm("ok"),
        transcript_max_messages=6,
    )

    for i in range(20):
        await service.take_turn(1, _user(), f"turn {i}")

    # Grows 2 at a time up to the cap, then plateaus — never exceeds it again.
    assert transcripts.save_sizes[:3] == [2, 4, 6]
    assert all(size == 6 for size in transcripts.save_sizes[3:])
    assert len(transcripts.save_sizes) == 20


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


class _ExplodingTts:
    async def synthesize(self, text: str) -> bytes:
        raise RuntimeError("tts provider down")


@pytest.mark.asyncio
async def test_stream_turn_survives_tts_failure_and_logs_it(caplog):
    # #236: a TTS failure degrades to no audio for that sentence (the text reply
    # already succeeded) rather than breaking the turn — but it must be logged, not
    # silently swallowed, so an operator can notice a pattern (e.g. an expired key).
    service = _service(
        _FakeSessions(owner_id=7),
        _FakeTranscripts(),
        _StreamingLlm(["Hi there."]),
        tts=_ExplodingTts(),
    )
    with caplog.at_level("WARNING"):
        events = [c async for c in service.stream_turn(1, _user(), "hello")]

    assert not any(isinstance(e, AudioChunk) for e in events)  # degraded, not raised
    assert any("tts" in r.message.lower() for r in caplog.records)
    assert caplog.records[0].exc_info is not None


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

        async def save(self, session_id, turns, *, commit=True):
            raise RuntimeError("db commit failed")

        async def commit(self):
            return None

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
