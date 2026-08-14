"""Score one minimal-pair production attempt (pure, deterministic).

Reuses the same normalization/presence rule as the shadowing scorer: a word is
"said" when its normalized form appears among the recognized words. We report the
target and the other word independently — a learner can say the target, the
other, both (rare), or neither.
"""

import re

from app.core.llm.interfaces import VerboseTranscript
from app.features.minimal_pairs.domain import PairAttemptResult

_WORD = re.compile(r"[a-z0-9']+")


def _normalize(word: str) -> str:
    return "".join(_WORD.findall(word.lower()))


def _heard_words(verbose: VerboseTranscript) -> set[str]:
    if verbose.words:
        return {_normalize(w.word) for w in verbose.words if _normalize(w.word)}
    # Fall back to the raw text when no per-word data is available.
    return {_normalize(w) for w in verbose.text.split() if _normalize(w)}


def score_pair_attempt(target: str, other: str, verbose: VerboseTranscript) -> PairAttemptResult:
    heard = _heard_words(verbose)
    return PairAttemptResult(
        transcript=verbose.text,
        said_target=_normalize(target) in heard,
        said_other=_normalize(other) in heard,
    )
