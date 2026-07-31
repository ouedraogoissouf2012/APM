"""What each `correction_intensity` MEANS, in one place (#114).

The learner picks "gentle" or "detailed" in their profile. That choice must
actually change the corrections they get — during the conversation (turn
corrector) AND in the debrief (analyzer). This module is the single source of
truth for that meaning, so the two engines stay consistent: a pure function maps
an intensity to a prompt directive + how many errors to surface.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CorrectionStyle:
    """How intensely to correct: a prompt directive + a cap on errors reported."""

    prompt_directive: str
    max_errors: int


_GENTLE = CorrectionStyle(
    prompt_directive=(
        "Correction style: GENTLE. Be warm and encouraging. Surface only the "
        "single most useful correction and keep explanations short — do not "
        "overwhelm the learner."
    ),
    max_errors=1,
)

_DETAILED = CorrectionStyle(
    prompt_directive=(
        "Correction style: DETAILED. Be thorough. Point out the most useful "
        "mistakes and give fuller explanations, with examples and alternatives, "
        "so the learner understands the underlying rules."
    ),
    max_errors=5,
)

# Keyed by str (not the Literal) so a stored/legacy value outside the closed set
# is a plain miss handled by the fallback, not a type error.
_STYLES: dict[str, CorrectionStyle] = {
    "gentle": _GENTLE,
    "detailed": _DETAILED,
}


def style_for_intensity(intensity: str) -> CorrectionStyle:
    """The correction style for a stored intensity value. An unknown value (e.g. a
    legacy row outside the closed set) falls back to the gentle style rather than
    crashing — the safe, less-overwhelming default."""
    return _STYLES.get(intensity, _GENTLE)
