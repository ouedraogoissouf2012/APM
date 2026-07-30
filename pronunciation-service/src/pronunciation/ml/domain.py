"""Pure domain types for phoneme-level pronunciation scoring — no torch, no I/O.

Keeping these framework-free lets the GOP and alignment logic be unit-tested on
plain Python lists (mocked emission log-probs) without loading the ~1 GB model.
"""

from dataclasses import dataclass

# The wav2vec2 model was trained at 16 kHz — audio MUST be resampled to this before
# inference. It is a model invariant, not a tunable setting (changing it corrupts
# results), so it lives here as the single source of truth shared by the transcoder
# (which resamples to it) and the model (which asserts it). DRY: one number, one place.
TARGET_SAMPLE_RATE = 16_000


@dataclass(frozen=True)
class PhonemeScore:
    """How well one expected phoneme was pronounced.

    - `phoneme`: the expected phoneme (IPA), e.g. "θ".
    - `score` in [0, 1]: goodness of pronunciation (higher = clearer).
    - `start`/`end`: frame indices this phoneme was aligned to (for debugging /
      future word grouping); frames, not seconds.
    """

    phoneme: str
    score: float
    start: int
    end: int
