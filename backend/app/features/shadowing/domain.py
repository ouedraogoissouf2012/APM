"""Pure domain types for shadowing (self-monitoring shadowing, #110).

The learner reads a target phrase aloud; we compare what a speech recognizer
heard against the target and surface the words that did not come through. This is
a WORD-level miss detector (did the word land intelligibly?), not fine phonetic
scoring — that is issue #111 (GOP/wav2vec2).
"""

from dataclasses import dataclass, field
from typing import Literal

# Which phonetic trap a target phrase drills, for French speakers of English.
# Kept as a closed set so the generator can't invent unstable labels.
PhoneticFocus = Literal[
    "th",  # /θ/ /ð/ — "think", "this"
    "h",  # aspirated h — "house" not "'ouse"
    "ship_sheep",  # /ɪ/ vs /iː/ — "ship" vs "sheep"
    "ed_endings",  # -ed endings — "worked", "wanted"
    "word_stress",  # tonic stress placement
    "general",  # no specific trap
]


@dataclass(frozen=True)
class ShadowingPhrase:
    """A phrase to read aloud, plus what it trains and one tip."""

    text: str
    focus: PhoneticFocus = "general"
    tip: str = ""


@dataclass(frozen=True)
class WordComparison:
    """One target word and whether the recognizer heard it."""

    target: str
    heard: bool


@dataclass(frozen=True)
class AttemptResult:
    """The outcome of one spoken attempt at a target phrase."""

    transcript: str
    words: list[WordComparison] = field(default_factory=list)
    missed_words: list[str] = field(default_factory=list)
    coaching: str = ""
