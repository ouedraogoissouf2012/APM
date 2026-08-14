"""Unit tests for the word-level pronunciation scorer (TDD, written first).

The scorer aligns the target phrase against Whisper's per-word transcript and
turns each target word into a clarity score:
- a word Whisper heard -> score derived from its recognition probability,
- a word Whisper missed -> score 0 (clearly not understood), high confidence,
- when Whisper gives no per-word probabilities -> score None (unknown), so the
  UI hides it rather than inventing a number.
"""

from app.core.llm.interfaces import TranscriptWord, VerboseTranscript
from app.features.pronunciation.scorer import score_words


def _by_word(scores):
    return {s.word: s for s in scores}


def test_a_heard_word_scores_one():
    # Whisper gives no probability (probability=None) -> heard means clear -> 1.0.
    verbose = VerboseTranscript(
        text="the ship is sinking",
        words=[
            TranscriptWord("the"),
            TranscriptWord("ship"),
            TranscriptWord("is"),
            TranscriptWord("sinking"),
        ],
    )
    ship = _by_word(score_words("The ship is sinking", verbose))["ship"]
    assert ship.score == 1.0
    assert ship.confidence is not None and ship.confidence > 0


def test_a_missed_word_scores_zero_with_confidence():
    # "ship" was not heard (learner said "sheep") -> score 0, we ARE confident.
    verbose = VerboseTranscript(
        text="the sheep is sinking",
        words=[
            TranscriptWord("the"),
            TranscriptWord("sheep"),
            TranscriptWord("is"),
            TranscriptWord("sinking"),
        ],
    )
    ship = _by_word(score_words("The ship is sinking", verbose))["ship"]
    assert ship.score == 0.0
    assert ship.confidence is not None and ship.confidence >= 0.5


def test_uses_a_real_probability_when_a_provider_supplies_one():
    # A future GOP engine that DOES give a per-word probability -> continuous score.
    verbose = VerboseTranscript(
        text="the ship",
        words=[TranscriptWord("the", 0.99), TranscriptWord("ship", 0.35)],
    )
    ship = _by_word(score_words("The ship", verbose))["ship"]
    assert ship.score is not None and ship.score < 0.6


def test_preserves_target_word_forms():
    verbose = VerboseTranscript(text="thoughtful", words=[TranscriptWord("thoughtful")])
    scores = score_words("Thoughtful", verbose)
    assert scores[0].word == "Thoughtful"


def test_empty_words_marks_every_target_unknown():
    # No word-level data at all (e.g. an STT that only returns text).
    scores = score_words("hello world", VerboseTranscript(text="hello world", words=[]))
    assert [s.word for s in scores] == ["hello", "world"]
    assert all(s.score is None for s in scores)


def test_repeated_target_word_matched_by_presence():
    # Two "the" targets but only one "the" heard -> first scores 1.0, second 0.0.
    verbose = VerboseTranscript(
        text="the cat dog",
        words=[TranscriptWord("the"), TranscriptWord("cat"), TranscriptWord("dog")],
    )
    scores = score_words("the cat the", verbose)
    the_scores = [s.score for s in scores if s.word == "the"]
    assert the_scores == [1.0, 0.0]
