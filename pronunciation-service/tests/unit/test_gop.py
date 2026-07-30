"""Unit tests for CTC forced alignment + GOP scoring (TDD, written first).

Everything here runs on tiny, hand-built emission log-prob matrices — no torch,
no model. This pins the SCIENTIFIC behaviour of the scorer:

- forced_align maps each target phoneme to the frames where the model emitted it,
  respecting CTC (a blank symbol separates/repeats labels).
- gop_scores turns a phoneme's posterior on its aligned frames into a [0,1]
  goodness score, normalized against the strongest competing phoneme.
"""

import math

from pronunciation.ml.gop import forced_align, gop_scores

# A 3-symbol alphabet for the tests: 0 = blank (CTC), 1 = "a", 2 = "b".
_BLANK = 0
_ID2PH = {1: "a", 2: "b"}


def _logprobs(rows: list[list[float]]) -> list[list[float]]:
    """Turn per-frame probability rows into log-probs (rows need not sum to 1;
    we only care about relative magnitudes for the tests)."""
    return [[math.log(p) if p > 0 else -100.0 for p in row] for row in rows]


def test_forced_align_maps_each_target_to_its_frames():
    # 4 frames. Target "a b". Frame 0-1 favour "a", frame 2 blank, frame 3 "b".
    log_probs = _logprobs(
        [
            [0.1, 0.8, 0.1],  # a
            [0.1, 0.8, 0.1],  # a
            [0.8, 0.1, 0.1],  # blank
            [0.1, 0.1, 0.8],  # b
        ]
    )
    segments = forced_align(log_probs, [1, 2], blank=_BLANK)
    assert len(segments) == 2  # one segment per target phoneme
    a_start, a_end = segments[0]
    b_start, b_end = segments[1]
    # "a" occupies the early frames, "b" the later — a strictly before b.
    assert a_start <= a_end < b_start <= b_end


def test_gop_high_when_phoneme_dominates_its_frames():
    # Target "a"; the model is very confident it's "a" on every frame.
    log_probs = _logprobs([[0.01, 0.98, 0.01]] * 3)
    scores = gop_scores(log_probs, [1], _ID2PH, blank=_BLANK)
    assert len(scores) == 1
    assert scores[0].phoneme == "a"
    assert scores[0].score > 0.8  # clearly pronounced


def test_gop_low_when_a_competitor_dominates():
    # Target is "a" but the model strongly hears "b" instead (confusion).
    log_probs = _logprobs([[0.01, 0.2, 0.79]] * 3)
    scores = gop_scores(log_probs, [1], _ID2PH, blank=_BLANK)
    assert scores[0].phoneme == "a"
    assert scores[0].score < 0.5  # poorly pronounced (heard the other phoneme)


def test_gop_scores_are_bounded_0_1():
    log_probs = _logprobs(
        [
            [0.1, 0.8, 0.1],
            [0.1, 0.1, 0.8],
        ]
    )
    for s in gop_scores(log_probs, [1, 2], _ID2PH, blank=_BLANK):
        assert 0.0 <= s.score <= 1.0


def test_gop_one_score_per_target_phoneme_in_order():
    log_probs = _logprobs([[0.1, 0.8, 0.1], [0.8, 0.1, 0.1], [0.1, 0.1, 0.8]])
    scores = gop_scores(log_probs, [1, 2], _ID2PH, blank=_BLANK)
    assert [s.phoneme for s in scores] == ["a", "b"]


def test_forced_align_requires_enough_frames():
    # Fewer frames than target phonemes -> cannot align; must not crash.
    log_probs = _logprobs([[0.1, 0.8, 0.1]])
    scores = gop_scores(log_probs, [1, 2], _ID2PH, blank=_BLANK)
    # Degrade gracefully: return a score per phoneme (0 for the unalignable one).
    assert len(scores) == 2
