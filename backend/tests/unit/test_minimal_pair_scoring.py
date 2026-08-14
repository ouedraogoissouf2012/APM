"""Unit tests for minimal-pair scoring (TDD, written first).

Given the target word and the other word of the pair, plus what Whisper heard,
decide: did they say the target? did they say the OTHER word instead? Both use
the same normalization/presence rule as the shadowing scorer.
"""

from app.core.llm.interfaces import TranscriptWord, VerboseTranscript
from app.features.minimal_pairs.pair_scoring import score_pair_attempt


def _verbose(*words: str) -> VerboseTranscript:
    return VerboseTranscript(
        text=" ".join(words),
        words=[TranscriptWord(w) for w in words],
    )


def test_said_the_target_word():
    result = score_pair_attempt(target="sheep", other="ship", verbose=_verbose("sheep"))
    assert result.said_target is True
    assert result.said_other is False


def test_said_the_other_word_instead():
    # The classic confusion: asked for "sheep", said "ship".
    result = score_pair_attempt(target="sheep", other="ship", verbose=_verbose("ship"))
    assert result.said_target is False
    assert result.said_other is True


def test_said_neither():
    result = score_pair_attempt(target="sheep", other="ship", verbose=_verbose("goat"))
    assert result.said_target is False
    assert result.said_other is False


def test_case_and_punctuation_insensitive():
    result = score_pair_attempt(target="Sheep", other="Ship", verbose=_verbose("SHEEP."))
    assert result.said_target is True


def test_target_inside_a_sentence():
    # Whisper may return a short phrase; presence of the word still counts.
    result = score_pair_attempt(target="think", other="sink", verbose=_verbose("i", "think", "so"))
    assert result.said_target is True
    assert result.said_other is False


def test_empty_transcript_is_neither():
    result = score_pair_attempt(target="sheep", other="ship", verbose=VerboseTranscript(text=""))
    assert result.said_target is False
    assert result.said_other is False


def test_transcript_preserved_on_result():
    result = score_pair_attempt(target="sheep", other="ship", verbose=_verbose("ship"))
    assert result.transcript == "ship"
