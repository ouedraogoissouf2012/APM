"""CTC forced alignment + Goodness-of-Pronunciation (GOP), in pure Python.

No torch, no model: the caller passes emission log-probs as plain nested lists
(frames x alphabet), so this scientific core is fully unit-testable without the
~1 GB acoustic model. The real service converts the model's logits to this shape.

Method:
- forced_align: standard CTC forced alignment. We build the extended label
  sequence blank, p1, blank, p2, blank, ... and run a Viterbi pass over the
  trellis (stay / advance-one / skip-a-blank-between-distinct-labels), then
  backtrack to assign each frame to a target phoneme (or the blank between them).
- gop_scores: for each target phoneme, its Goodness of Pronunciation is the mean
  per-frame posterior of that phoneme over the frames it was aligned to,
  normalized to [0,1] against the best competing phoneme (Witt & Young style,
  via a softmax over the alphabet on those frames).
"""

import math

from pronunciation.ml.domain import PhonemeScore

_NEG_INF = float("-inf")


def forced_align(
    log_probs: list[list[float]], target_ids: list[int], blank: int = 0
) -> list[tuple[int, int]]:
    """Align each target phoneme to a contiguous [start, end] frame span.

    Returns one (start, end) per target id, in order. When there are fewer frames
    than needed, unalignable trailing phonemes get an empty span (start > end).
    """
    frames = len(log_probs)
    n = len(target_ids)
    if n == 0:
        return []
    # Not enough frames to place every label: align greedily what we can, and
    # mark the rest empty (the caller scores those 0 — graceful degradation).
    if frames < n:
        spans: list[tuple[int, int]] = [(i, i) for i in range(min(frames, n))]
        spans += [(frames, frames - 1) for _ in range(n - len(spans))]  # empty spans
        return spans

    # Extended sequence: blank, t0, blank, t1, ..., blank. Length 2n+1.
    ext = [blank]
    for t in target_ids:
        ext += [t, blank]
    s_len = len(ext)

    # Viterbi over the trellis. dp[f][s] = best log-prob of aligning frames[0..f]
    # ending in extended-position s. back[f][s] = predecessor s.
    dp = [[_NEG_INF] * s_len for _ in range(frames)]
    back = [[-1] * s_len for _ in range(frames)]

    dp[0][0] = log_probs[0][ext[0]]
    if s_len > 1:
        dp[0][1] = log_probs[0][ext[1]]

    for f in range(1, frames):
        for s in range(s_len):
            best_prev, best_s = _NEG_INF, -1
            # stay on s
            if dp[f - 1][s] > best_prev:
                best_prev, best_s = dp[f - 1][s], s
            # advance from s-1
            if s >= 1 and dp[f - 1][s - 1] > best_prev:
                best_prev, best_s = dp[f - 1][s - 1], s - 1
            # skip a blank from s-2, only between two DISTINCT non-blank labels
            if s >= 2 and ext[s] != blank and ext[s] != ext[s - 2] and dp[f - 1][s - 2] > best_prev:
                best_prev, best_s = dp[f - 1][s - 2], s - 2
            if best_s != -1:
                dp[f][s] = best_prev + log_probs[f][ext[s]]
                back[f][s] = best_s

    # End in one of the two final positions (last label or trailing blank).
    end_s = s_len - 1 if dp[frames - 1][s_len - 1] >= dp[frames - 1][s_len - 2] else s_len - 2
    path = [0] * frames
    s = end_s
    for f in range(frames - 1, -1, -1):
        path[f] = s
        s = back[f][s]

    # Collect frame spans per target phoneme (odd positions in ext are labels:
    # ext[1], ext[3], ... correspond to target_ids[0], target_ids[1], ...).
    spans = []
    for i in range(n):
        pos = 2 * i + 1  # position of target i in the extended sequence
        assigned = [f for f in range(frames) if path[f] == pos]
        if assigned:
            spans.append((assigned[0], assigned[-1]))
        else:
            spans.append((frames, frames - 1))  # empty span
    return spans


def gop_scores(
    log_probs: list[list[float]],
    target_ids: list[int],
    id_to_phoneme: dict[int, str],
    blank: int = 0,
) -> list[PhonemeScore]:
    """Goodness of Pronunciation per target phoneme, in [0, 1]."""
    spans = forced_align(log_probs, target_ids, blank=blank)
    scores: list[PhonemeScore] = []
    for target_id, (start, end) in zip(target_ids, spans, strict=True):
        phoneme = id_to_phoneme.get(target_id, "?")
        if start > end:  # unalignable -> not pronounced
            scores.append(PhonemeScore(phoneme=phoneme, score=0.0, start=start, end=end))
            continue
        # GOP (Witt & Young): compare the TARGET phoneme's log-posterior to the
        # BEST competing phoneme's, per frame, then average. This is the calibrated
        # signal — a raw posterior is unfair when two phonemes share probability
        # mass (e.g. the model splits /θ/ and /f/, crushing /θ/ to ~0.08 even when
        # correctly pronounced). The ratio asks the right question: "did the target
        # win, or did a competitor?" — independent of how many phonemes competed.
        gops = [_gop_at(log_probs[f], target_id, blank) for f in range(start, end + 1)]
        gop = sum(gops) / len(gops)
        scores.append(
            PhonemeScore(phoneme=phoneme, score=round(_gop_to_score(gop), 3), start=start, end=end)
        )
    return scores


def _gop_at(row: list[float], target_id: int, blank: int) -> float:
    """GOP for one frame: log P(target) - log P(best competitor).

    0 means the target is (tied for) the most likely phoneme — a clear pronunciation.
    Negative means a competitor was more likely — the more negative, the worse. The
    blank symbol is excluded from the competition (it carries no phonetic identity)."""
    target_lp = row[target_id]
    best_competitor_lp = _NEG_INF
    for i, lp in enumerate(row):
        if i in (target_id, blank):
            continue
        if lp > best_competitor_lp:
            best_competitor_lp = lp
    if best_competitor_lp == _NEG_INF:  # no competitor (degenerate alphabet)
        return 0.0
    return target_lp - best_competitor_lp


def _gop_to_score(gop: float) -> float:
    """Map a GOP value (<= 0 typically) to a [0,1] goodness score via a logistic.

    Calibrated on REAL model behaviour (measured, not guessed): this multilingual
    model splits probability mass between confusable phonemes, so even a correctly
    pronounced /θ/ scores GOP ~ -2.1, while a truly wrong one (said "sink") scores
    ~ -4.8. The center at -3.0 puts the boundary between the two, so a correct sound
    lands in the review/strong band and a wrong one in "needs practice":

    gop >= -1.5 (target ~ the winner)  -> ~0.9  (strong)
    gop = -2.1  (correct, confusable)  -> ~0.8  (review/strong)
    gop = -3.0  (boundary)             ->  0.5
    gop <= -4.8 (competitor dominates) -> ~0.06 (needs practice)"""
    return 1.0 / (1.0 + math.exp(-(gop + 3.0) * 1.5))


def _softmax_at(row: list[float], index: int) -> float:
    """Softmax probability of `index` given a row of log-probs (numerically stable)."""
    m = max(row)
    exps = [math.exp(v - m) for v in row]
    total = sum(exps)
    return exps[index] / total if total > 0 else 0.0
