"""#379: onboarding reuses the debrief analyzer for placement CEFR estimation
(see dependencies.py's own comment), so it must ALSO get
debrief_max_learner_turns wired — mirroring debrief's DI site (both were
missing it before this fix).
"""

from app.config import get_settings
from app.features.onboarding.dependencies import get_onboarding_service


def _analyzer_caps(service):
    analyzer = service._analyzer  # White-box: no public getter.
    return analyzer._max_errors, analyzer._max_learner_turns


def test_wires_the_configured_error_and_learner_turn_caps():
    settings = get_settings()
    service = get_onboarding_service(db=None)
    assert _analyzer_caps(service) == (
        settings.debrief_max_errors,
        settings.debrief_max_learner_turns,
    )


def test_a_changed_learner_turn_cap_setting_reaches_the_analyzer(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "debrief_max_learner_turns", 7)
    service = get_onboarding_service(db=None)
    assert service._analyzer._max_learner_turns == 7
