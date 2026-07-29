"""Pure domain types for the minimal-pairs drill (#112).

The learner is asked to produce one word of a minimal pair (e.g. "sheep" from
ship/sheep). We check whether they said the target, and — the pedagogical point —
whether they said the OTHER word of the pair instead (the classic FR→EN
confusion). Recognition is Whisper word-presence, not fine phonetic scoring.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PairAttemptResult:
    """Outcome of producing one word of a minimal pair."""

    transcript: str
    said_target: bool  # the target word was heard
    said_other: bool  # the OTHER word of the pair was heard instead
    coaching: str = ""
