"""Unit tests for the correction-intensity style (pure, no LLM).

`correction_intensity` (gentle | detailed) is a learner profile setting that must
actually change how corrections are produced — it was stored and editable but
never used (#114). This module is the single source of what each intensity MEANS,
shared by the turn corrector and the debrief analyzer, so the two never drift.
"""

from app.features.profile.correction_style import (
    CorrectionStyle,
    style_for_intensity,
)


def test_gentle_reports_fewer_errors_than_detailed():
    gentle = style_for_intensity("gentle")
    detailed = style_for_intensity("detailed")
    assert gentle.max_errors < detailed.max_errors


def test_gentle_directive_asks_for_a_soft_single_correction():
    directive = style_for_intensity("gentle").prompt_directive
    lowered = directive.lower()
    assert "gentle" in lowered or "encouraging" in lowered
    # Gentle = at most one correction.
    assert "one" in lowered or "single" in lowered


def test_detailed_directive_asks_for_more_and_fuller_explanations():
    directive = style_for_intensity("detailed").prompt_directive.lower()
    assert "detailed" in directive or "thorough" in directive


def test_unknown_intensity_falls_back_to_gentle():
    # Defensive: a stored value outside the closed set must not crash; default to
    # the safe, less-overwhelming style.
    assert style_for_intensity("bogus") == style_for_intensity("gentle")


def test_returns_a_correction_style_dataclass():
    style = style_for_intensity("detailed")
    assert isinstance(style, CorrectionStyle)
    assert style.max_errors >= 1
    assert style.prompt_directive  # non-empty guidance
