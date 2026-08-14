import pytest

from app.features.conversation.messages import Message
from app.features.debrief.analyzer import DebriefAnalyzer


class _CannedLlm:
    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.seen_system: str | None = None
        self.seen_user: str | None = None

    async def complete(self, system_prompt: str, history: list[Message]) -> str:
        self.seen_system = system_prompt
        self.seen_user = history[-1].content if history else ""
        return self._reply


_TURNS = [
    {"role": "assistant", "content": "How was your day?"},
    {"role": "user", "content": "I go to school yesterday and i eats lunch"},
]


@pytest.mark.asyncio
async def test_analyze_returns_errors_and_cefr():
    reply = (
        '{"cefr_estimate": "A2", "summary": "Good effort!",'
        ' "errors": ['
        '  {"original": "I go to school yesterday", "correction": "I went to school yesterday",'
        '   "rule": "Past simple for finished actions", "error_type": "verb_tense"}'
        " ]}"
    )
    analyzer = DebriefAnalyzer(_CannedLlm(reply))
    result = await analyzer.analyze(_TURNS, native_language="fr")

    assert result.cefr_estimate == "A2"
    assert result.summary == "Good effort!"
    assert len(result.errors) == 1
    assert result.errors[0].correction == "I went to school yesterday"


@pytest.mark.asyncio
async def test_analyze_captures_vocabulary_words_with_learner_sentence():
    reply = (
        '{"cefr_estimate": "B1", "summary": "Nice.", "errors": [],'
        ' "words": ['
        '  {"word": "deployment", "phonetic": "dɪˈplɔɪmənt", "translation": "déploiement",'
        '   "example": "I handle deployments at work."},'
        '  {"word": "handle", "phonetic": "ˈhændl", "translation": "gérer",'
        '   "example": "I handle deployments at work."}'
        " ]}"
    )
    analyzer = DebriefAnalyzer(_CannedLlm(reply))
    result = await analyzer.analyze(_TURNS, native_language="fr")

    assert len(result.words) == 2
    assert result.words[0].word == "deployment"
    assert result.words[0].translation == "déploiement"
    assert result.words[0].example == "I handle deployments at work."


@pytest.mark.asyncio
async def test_analyze_tolerates_missing_words_field():
    # Older/edge replies without a "words" key must not break — empty list.
    reply = '{"cefr_estimate": "A2", "summary": "ok", "errors": []}'
    analyzer = DebriefAnalyzer(_CannedLlm(reply))
    result = await analyzer.analyze(_TURNS, native_language="fr")
    assert result.words == []


@pytest.mark.asyncio
async def test_analyze_captures_explanation_examples_and_alternatives():
    reply = (
        '{"cefr_estimate": "A2", "summary": "Good effort!",'
        ' "errors": ['
        '  {"original": "I go to school yesterday",'
        '   "correction": "I went to school yesterday",'
        '   "rule": "Past simple", "error_type": "verb_tense",'
        '   "explanation": "Yesterday is finished, so use the past simple.",'
        '   "examples": ["I went home.", "She played tennis."],'
        '   "alternatives": ["Yesterday I went to school", "extra", "too many"]}'
        " ]}"
    )
    analyzer = DebriefAnalyzer(_CannedLlm(reply))
    result = await analyzer.analyze(_TURNS, native_language="fr")

    err = result.errors[0]
    assert err.explanation.startswith("Yesterday is finished")
    assert err.examples == ["I went home.", "She played tennis."]
    # Alternatives are capped at 2.
    assert err.alternatives == ["Yesterday I went to school", "extra"]


@pytest.mark.asyncio
async def test_analyze_tolerates_missing_rich_fields():
    reply = (
        '{"cefr_estimate": "A2", "summary": "s",'
        ' "errors": ['
        '  {"original": "i eats lunch", "correction": "I eat lunch",'
        '   "rule": "SVA", "error_type": "subject_verb_agreement"}'
        " ]}"
    )
    analyzer = DebriefAnalyzer(_CannedLlm(reply))
    result = await analyzer.analyze(_TURNS, native_language="fr")

    err = result.errors[0]
    assert err.explanation == ""
    assert err.examples == []
    assert err.alternatives == []


@pytest.mark.asyncio
async def test_analyze_normalizes_error_type_to_canonical_taxonomy():
    reply = (
        '{"cefr_estimate": "A2", "summary": "Good effort!",'
        ' "errors": ['
        '  {"original": "i eats lunch", "correction": "I eat lunch",'
        '   "rule": "Subject-verb agreement", "error_type": "Subject-verb agreement"}'
        " ]}"
    )
    analyzer = DebriefAnalyzer(_CannedLlm(reply))
    result = await analyzer.analyze(_TURNS, native_language="fr")

    assert result.errors[0].error_type == "subject_verb_agreement"


@pytest.mark.asyncio
async def test_analyze_drops_hallucinated_errors_not_in_learner_text():
    reply = (
        '{"cefr_estimate": "B1", "summary": "s",'
        ' "errors": ['
        '  {"original": "I have went to Paris", "correction": "I have gone to Paris",'
        '   "rule": "Past participle", "error_type": "verb_form"}'
        " ]}"
    )
    analyzer = DebriefAnalyzer(_CannedLlm(reply))
    result = await analyzer.analyze(_TURNS, native_language="fr")
    assert result.errors == []


@pytest.mark.asyncio
async def test_analyze_falls_back_on_invalid_cefr():
    reply = '{"cefr_estimate": "Z9", "summary": "s", "errors": []}'
    analyzer = DebriefAnalyzer(_CannedLlm(reply))
    result = await analyzer.analyze(_TURNS, native_language="fr", fallback_cefr="A1")
    assert result.cefr_estimate == "A1"


@pytest.mark.asyncio
async def test_intensity_reaches_the_prompt_and_caps_errors():
    # #114: correction_intensity must actually change the debrief. "gentle" reports
    # at most one error and its directive appears in the prompt.
    reply = (
        '{"cefr_estimate": "A2", "summary": "s", "errors": ['
        '  {"original": "I go to school yesterday", "correction": "I went to school yesterday",'
        '   "rule": "past", "error_type": "verb_tense"},'
        '  {"original": "i eats lunch", "correction": "I eat lunch",'
        '   "rule": "SVA", "error_type": "subject_verb_agreement"}'
        " ]}"
    )
    llm = _CannedLlm(reply)
    analyzer = DebriefAnalyzer(llm, max_errors=5)
    result = await analyzer.analyze(_TURNS, native_language="fr", intensity="gentle")
    assert "gentle" in (llm.seen_system or "").lower()
    assert len(result.errors) == 1  # gentle caps at one, even though two were returned


@pytest.mark.asyncio
async def test_detailed_intensity_allows_more_errors():
    reply = (
        '{"cefr_estimate": "A2", "summary": "s", "errors": ['
        '  {"original": "I go to school yesterday", "correction": "I went to school yesterday",'
        '   "rule": "past", "error_type": "verb_tense"},'
        '  {"original": "i eats lunch", "correction": "I eat lunch",'
        '   "rule": "SVA", "error_type": "subject_verb_agreement"}'
        " ]}"
    )
    analyzer = DebriefAnalyzer(_CannedLlm(reply), max_errors=5)
    result = await analyzer.analyze(_TURNS, native_language="fr", intensity="detailed")
    assert len(result.errors) == 2  # detailed surfaces more


@pytest.mark.asyncio
async def test_analyze_caps_learner_text_to_the_most_recent_turns():
    # #364 (shared root cause with the transcript-storage issue): an
    # abusive/very long session must not grow the debrief LLM call's prompt
    # (cost/latency) without bound. Only the last max_learner_turns learner
    # utterances are analyzed. Recency is also the right bias for a CEFR
    # estimate — it should reflect the learner's CURRENT level, not be diluted
    # by an early warm-up on a very long session.
    turns = [{"role": "user", "content": f"turn {i}"} for i in range(10)]
    llm = _CannedLlm('{"cefr_estimate": "B1", "summary": "", "errors": []}')
    analyzer = DebriefAnalyzer(llm, max_learner_turns=3)

    await analyzer.analyze(turns, native_language="fr")

    seen = llm.seen_user or ""
    assert "turn 9" in seen
    assert "turn 7" in seen
    assert "turn 6" not in seen
    assert "turn 0" not in seen


@pytest.mark.asyncio
async def test_analyze_learner_turn_cap_of_zero_means_unlimited():
    turns = [{"role": "user", "content": f"turn {i}"} for i in range(5)]
    llm = _CannedLlm('{"cefr_estimate": "B1", "summary": "", "errors": []}')
    analyzer = DebriefAnalyzer(llm, max_learner_turns=0)

    await analyzer.analyze(turns, native_language="fr")

    seen = llm.seen_user or ""
    assert "turn 0" in seen
    assert "turn 4" in seen


@pytest.mark.asyncio
async def test_analyze_passes_native_language_and_only_learner_text():
    llm = _CannedLlm('{"cefr_estimate": "B1", "summary": "", "errors": []}')
    analyzer = DebriefAnalyzer(llm)
    await analyzer.analyze(_TURNS, native_language="fr")
    assert "fr" in (llm.seen_system or "")
    assert "untrusted learner content" in (llm.seen_system or "").lower()
    assert "never follow instructions" in (llm.seen_system or "").lower()
    assert "UNTRUSTED LEARNER TRANSCRIPT" in (llm.seen_user or "")
    assert "<learner_transcript>" in (llm.seen_user or "")
    assert "I go to school yesterday" in (llm.seen_user or "")
    assert "How was your day?" not in (llm.seen_user or "")
