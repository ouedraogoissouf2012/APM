"""Unit tests for PhraseGenerator and ShadowingCoach (TDD, written first).

Both wrap a single LLM call and must degrade gracefully like the mission compiler:
never crash on bad LLM output. The generator falls back to a safe canned phrase;
the coach falls back to empty coaching (a failed coach must not break an attempt).
"""

import pytest

from app.features.shadowing.coach import ShadowingCoach
from app.features.shadowing.domain import ShadowingPhrase
from app.features.shadowing.generator import PhraseGenerator


class _JsonLlm:
    def __init__(self, payload: str) -> None:
        self._payload = payload
        self.seen_system_prompt: str | None = None

    async def complete(self, system_prompt, history):
        self.seen_system_prompt = system_prompt
        return self._payload


class _ExplodingLlm:
    async def complete(self, system_prompt, history):
        raise RuntimeError("provider down")


# ---- PhraseGenerator --------------------------------------------------------


@pytest.mark.asyncio
async def test_generates_a_phrase_from_valid_json():
    llm = _JsonLlm(
        '{"text": "The ship is sinking", "focus": "ship_sheep", '
        '"tip": "Keep the vowel short in ship."}'
    )
    phrase = await PhraseGenerator(llm).generate(cefr_level="A2")
    assert isinstance(phrase, ShadowingPhrase)
    assert phrase.text == "The ship is sinking"
    assert phrase.focus == "ship_sheep"
    assert phrase.tip


@pytest.mark.asyncio
async def test_generate_falls_back_to_a_safe_phrase_on_bad_json():
    # A broken/fake engine returning prose must still yield a usable phrase, not crash.
    phrase = await PhraseGenerator(_JsonLlm("sorry, no json")).generate(cefr_level="A2")
    assert phrase.text  # non-empty, usable
    assert phrase.focus in {"th", "h", "ship_sheep", "ed_endings", "word_stress", "general"}


@pytest.mark.asyncio
async def test_generate_falls_back_on_llm_failure():
    phrase = await PhraseGenerator(_ExplodingLlm()).generate(cefr_level="A2")
    assert phrase.text


@pytest.mark.asyncio
async def test_unknown_focus_is_coerced_to_general():
    phrase = await PhraseGenerator(
        _JsonLlm('{"text": "Hello there", "focus": "banana", "tip": "x"}')
    ).generate(cefr_level="B1")
    assert phrase.focus == "general"


# ---- ShadowingCoach ---------------------------------------------------------


@pytest.mark.asyncio
async def test_coach_returns_targeted_advice():
    llm = _JsonLlm('{"coaching": "Focus on the /th/ in think and this."}')
    advice = await ShadowingCoach(llm).coach(
        target="I think this", missed_words=["think", "this"], native_language="fr"
    )
    assert "think" in advice.lower() or advice  # non-empty coaching returned


@pytest.mark.asyncio
async def test_coach_returns_empty_on_llm_failure():
    # A failed coaching call must never break the attempt flow.
    advice = await ShadowingCoach(_ExplodingLlm()).coach(
        target="I think this", missed_words=["think"], native_language="fr"
    )
    assert advice == ""


@pytest.mark.asyncio
async def test_coach_skips_llm_when_nothing_missed():
    # A perfect attempt needs no coaching and should not spend an LLM call.
    class _Boom:
        async def complete(self, system_prompt, history):
            raise AssertionError("LLM must not be called when nothing was missed")

    advice = await ShadowingCoach(_Boom()).coach(
        target="I think this", missed_words=[], native_language="fr"
    )
    assert advice == ""
