import pytest

from app.features.conversation.correction import TurnCorrection, TurnCorrector


class _JsonLlm:
    """Returns a canned string (usually JSON) for the correction prompt."""

    def __init__(self, payload: str) -> None:
        self._payload = payload
        self.seen_history = None

    async def complete(self, system_prompt, history):
        self.seen_history = history
        return self._payload


class _ExplodingLlm:
    async def complete(self, system_prompt, history):
        raise RuntimeError("provider down")


async def _correct(payload: str, text: str = "i is happy"):
    return await TurnCorrector(_JsonLlm(payload)).correct(text, "A2", "fr")


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
