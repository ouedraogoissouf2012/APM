"""Unit tests for the target-vs-transcript word diff (TDD, written first).

The rules this pins down:
- comparison is case-insensitive and ignores punctuation,
- each target word is matched at most once against the heard words (in order),
- a word the recognizer did not hear is reported as missed,
- extra heard words are ignored (we only report on the target).
"""

from app.features.shadowing.diff import compare_words


def _missed(target: str, transcript: str) -> list[str]:
    return [w.target for w in compare_words(target, transcript) if not w.heard]


def test_perfect_match_has_no_missed_words():
    words = compare_words("The ship is sinking", "the ship is sinking")
    assert all(w.heard for w in words)
    assert [w.target for w in words] == ["The", "ship", "is", "sinking"]


def test_ignores_case_and_punctuation():
    assert _missed("The ship is sinking!", "THE SHIP IS SINKING.") == []


def test_reports_a_word_the_recognizer_missed():
    # "sheep" heard instead of "ship" -> "ship" is missed.
    assert _missed("The ship is here", "the sheep is here") == ["ship"]


def test_reports_multiple_missed_words():
    assert _missed("I think this house", "I sink dis ouse") == ["think", "this", "house"]


def test_extra_heard_words_do_not_create_misses():
    # The learner added a filler word; every target word is still present.
    assert _missed("I am ready", "um I am really ready") == []


def test_repeated_target_word_matched_once_each():
    # Two "the" in the target, only one heard -> one still missed.
    missed = _missed("the cat the dog", "the cat a dog")
    assert missed == ["the"]


def test_empty_transcript_misses_everything():
    assert _missed("hello world", "") == ["hello", "world"]


def test_preserves_original_target_spelling_in_output():
    # Output keeps the target's original casing/word form, not the normalized one.
    words = compare_words("Thoughtful", "thoughtful")
    assert words[0].target == "Thoughtful"
