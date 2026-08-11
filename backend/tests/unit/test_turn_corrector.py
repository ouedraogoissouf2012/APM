import pytest

from app.features.conversation.correction import TurnCorrection, TurnCorrector


class _JsonLlm:
    """Returns a canned string (usually JSON) for the correction prompt."""

    def __init__(self, payload: str) -> None:
        self._payload = payload
        self.seen_history = None
        self.seen_system_prompt = None

    async def complete(self, system_prompt, history):
        self.seen_history = history
        self.seen_system_prompt = system_prompt
        return self._payload


class _ExplodingLlm:
    async def complete(self, system_prompt, history):
        raise RuntimeError("provider down")


async def _correct(payload: str, text: str = "i is happy", intensity: str = "gentle"):
    return await TurnCorrector(_JsonLlm(payload)).correct(text, "A2", "fr", intensity)


@pytest.mark.asyncio
async def test_intensity_directive_is_included_in_the_prompt():
    # #114: the learner's correction_intensity must actually reach the prompt.
    llm = _JsonLlm('{"has_error": false}')
    await TurnCorrector(llm).correct("i is happy", "A2", "fr", "detailed")
    assert "detailed" in llm.seen_system_prompt.lower()


@pytest.mark.asyncio
async def test_skips_the_llm_for_very_short_utterances():
    # #123 cost control: a 1-2 word utterance ("yes", "ok thanks") rarely has a
    # worthwhile correction; skip the 2nd LLM call entirely.
    llm = _JsonLlm('{"has_error": true, "original": "ok", "correction": "OK", "rule": "r"}')
    result = await TurnCorrector(llm, min_words=3).correct("ok thanks", "A2", "fr")
    assert result is None
    assert llm.seen_system_prompt is None  # the LLM was never called


@pytest.mark.asyncio
async def test_corrects_normally_when_utterance_is_long_enough():
    llm = _JsonLlm(
        '{"has_error": true, "original": "i is happy", "correction": "I am happy", "rule": "r"}'
    )
    result = await TurnCorrector(llm, min_words=3).correct("i is happy today", "A2", "fr")
    assert result is not None
    assert llm.seen_system_prompt is not None  # long enough -> LLM was called


@pytest.mark.asyncio
async def test_returns_correction_when_a_real_mistake_is_present():
    result = await _correct(
        '{"has_error": true, "original": "i is happy", '
        '"correction": "I am happy", "rule": "Use \'am\' with \'I\'.", '
        '"alternatives": ["I feel happy", "I\'m happy"]}'
    )
    assert result == TurnCorrection(
        original="i is happy",
        correction="I am happy",
        rule="Use 'am' with 'I'.",
        alternatives=["I feel happy", "I'm happy"],
    )


@pytest.mark.asyncio
async def test_returns_none_when_no_error():
    assert await _correct('{"has_error": false}') is None


@pytest.mark.asyncio
async def test_rejects_correction_not_anchored_in_the_utterance():
    # Anti-hallucination: 'original' must be a verbatim substring of what was said.
    result = await _correct(
        '{"has_error": true, "original": "she goes", '
        '"correction": "she went", "rule": "past tense"}',
        text="i is happy",
    )
    assert result is None


@pytest.mark.asyncio
async def test_rejects_no_op_correction():
    result = await _correct(
        '{"has_error": true, "original": "i is happy", "correction": "i is happy", "rule": "x"}'
    )
    assert result is None


@pytest.mark.asyncio
async def test_caps_alternatives_to_two():
    result = await _correct(
        '{"has_error": true, "original": "i is happy", "correction": "I am happy", '
        '"rule": "r", "alternatives": ["a", "b", "c", "d"]}'
    )
    assert result is not None
    assert result.alternatives == ["a", "b"]


@pytest.mark.asyncio
async def test_non_json_output_yields_no_correction():
    # The fake engine returns "You said: ..." — must degrade to no correction.
    assert await _correct("You said: i is happy") is None


@pytest.mark.asyncio
async def test_llm_failure_yields_no_correction():
    result = await TurnCorrector(_ExplodingLlm()).correct("i is happy", "A2", "fr")
    assert result is None


@pytest.mark.asyncio
async def test_llm_failure_is_logged(caplog):
    # #236: a swallowed correction failure must leave a server-side trace, not
    # disappear silently — the learner loses the correction chip either way, but
    # only a log lets an operator notice a pattern (e.g. an expired API key).
    with caplog.at_level("WARNING"):
        await TurnCorrector(_ExplodingLlm()).correct("i is happy", "A2", "fr")
    assert any("correction" in r.message.lower() for r in caplog.records)
    assert caplog.records[0].exc_info is not None


@pytest.mark.asyncio
async def test_malformed_correction_response_is_logged(caplog, monkeypatch):
    # #238/#236: the try/except around field extraction is a backstop for any type
    # surprise from a free-form LLM the explicit guards don't already catch — force
    # that backstop to trigger and assert it logs, not just silently returns None.
    import app.features.conversation.correction as correction_module

    def _boom(text):
        raise ValueError("simulated parse-stage failure")

    monkeypatch.setattr(correction_module, "_loads", _boom)

    with caplog.at_level("WARNING"):
        result = await TurnCorrector(_JsonLlm('{"has_error": true}')).correct(
            "i is happy", "A2", "fr"
        )
    assert result is None
    assert any("pars" in r.message.lower() for r in caplog.records)


@pytest.mark.asyncio
async def test_mistyped_alternatives_does_not_crash_the_turn():
    # #238: a syntactically valid but wrongly-TYPED field ("alternatives": 5) used
    # to raise a TypeError (for a in 5) OUTSIDE the try — breaking the whole turn.
    # It must now degrade gracefully: the correction still stands, sans alternatives.
    result = await _correct(
        '{"has_error": true, "original": "i is happy", "correction": "I am happy", '
        '"rule": "r", "alternatives": 5}'
    )
    assert result is not None
    assert result.correction == "I am happy"
    assert result.alternatives == []  # the bad field is ignored, not fatal


@pytest.mark.asyncio
async def test_string_alternatives_are_not_split_into_characters():
    # A string (not a list) must NOT be iterated into per-character "alternatives".
    result = await _correct(
        '{"has_error": true, "original": "i is happy", "correction": "I am happy", '
        '"rule": "r", "alternatives": "I feel happy"}'
    )
    assert result is not None
    assert result.alternatives == []
