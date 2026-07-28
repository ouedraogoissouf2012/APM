"""Compare a target phrase against what a speech recognizer heard.

Pure, deterministic, no I/O. This is a word-presence check: for each target word,
was it heard (case/punctuation-insensitive)? Each target word consumes at most one
matching heard word, scanning left to right, so a repeated target word is only
satisfied as many times as it was actually heard. Extra heard words are ignored —
we only report on the target.
"""

import re

from app.features.shadowing.domain import WordComparison

_WORD = re.compile(r"[a-z0-9']+")


def _tokens(text: str) -> list[str]:
    """Lower-case word tokens, punctuation stripped."""
    return _WORD.findall(text.lower())


def compare_words(target: str, transcript: str) -> list[WordComparison]:
    heard_remaining = _tokens(transcript)
    # Multiset of heard words, consumed as we match, so each heard token satisfies
    # at most one target word.
    available: dict[str, int] = {}
    for token in heard_remaining:
        available[token] = available.get(token, 0) + 1

    comparisons: list[WordComparison] = []
    # Keep the target's original word forms for display; normalize only to match.
    for raw_word in target.split():
        normalized = "".join(_WORD.findall(raw_word.lower()))
        if not normalized:
            continue
        heard = available.get(normalized, 0) > 0
        if heard:
            available[normalized] -= 1
        comparisons.append(WordComparison(target=raw_word, heard=heard))
    return comparisons


def missed_words(comparisons: list[WordComparison]) -> list[str]:
    return [c.target for c in comparisons if not c.heard]
