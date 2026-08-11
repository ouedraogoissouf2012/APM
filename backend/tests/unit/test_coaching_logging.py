"""#236: a swallowed coaching/generation LLM failure must log a server-side trace,
not disappear silently — the learner loses the tip either way, but only a log
lets an operator notice a pattern (e.g. an expired API key)."""

import pytest

from app.features.minimal_pairs.coach import PairCoach
from app.features.shadowing.coach import ShadowingCoach
from app.features.shadowing.generator import PhraseGenerator


class _ExplodingLlm:
    async def complete(self, system_prompt, history):
        raise RuntimeError("provider down")


@pytest.mark.asyncio
async def test_shadowing_coach_failure_is_logged(caplog):
    with caplog.at_level("WARNING"):
        result = await ShadowingCoach(_ExplodingLlm()).coach("The ship is sinking", ["ship"], "fr")
    assert result == ""
    assert any("coach" in r.message.lower() for r in caplog.records)
    assert caplog.records[0].exc_info is not None


@pytest.mark.asyncio
async def test_minimal_pairs_coach_failure_is_logged(caplog):
    with caplog.at_level("WARNING"):
        result = await PairCoach(_ExplodingLlm()).coach("sheep", "ship", True, "fr")
    assert result == ""
    assert any("coach" in r.message.lower() for r in caplog.records)
    assert caplog.records[0].exc_info is not None


@pytest.mark.asyncio
async def test_shadowing_generator_failure_is_logged(caplog):
    with caplog.at_level("WARNING"):
        phrase = await PhraseGenerator(_ExplodingLlm()).generate("A2")
    # Falls back to a canned phrase, but the failure must still be traced.
    assert phrase.text  # a fallback phrase was returned
    assert any("generat" in r.message.lower() for r in caplog.records)
    assert caplog.records[0].exc_info is not None
