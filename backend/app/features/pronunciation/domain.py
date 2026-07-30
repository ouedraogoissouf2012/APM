"""Pure domain types for pronunciation scoring (#111).

A WordScore says, for one target word, how clearly the learner produced it. Today
the signal is Whisper's per-word recognition confidence (did the word come through
clearly?), NOT fine phonetic quality — that is a later engine (GOP/wav2vec2). The
`confidence` field lets the UI hide scores that are not trustworthy.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WordScore:
    """Pronunciation clarity for one target word.

    - `score` in [0,1]: how clearly the word was recognized (None if unknown).
    - `confidence` in [0,1]: how much to trust this score (None = unknown, the UI
      treats it as reliable). A missed word gets score 0 with high confidence.
    """

    word: str
    score: float | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class PhonemeScore:
    """Goodness-of-Pronunciation for one expected phoneme (#111 step 2).

    Produced by the GOP microservice (wav2vec2), a finer signal than WordScore:
    it says how well one IPA phoneme was pronounced, e.g. the /θ/ in "think".

    - `phoneme`: the expected IPA phoneme, e.g. "θ".
    - `score` in [0,1]: goodness of pronunciation (higher = clearer).

    Honest limitation carried from the engine: this is a raw ACOUSTIC score, not
    calibrated on French-speaker voices — the UI must show it with uncertainty,
    never as an absolute verdict (see the microservice README's tracked debt)."""

    phoneme: str
    score: float
