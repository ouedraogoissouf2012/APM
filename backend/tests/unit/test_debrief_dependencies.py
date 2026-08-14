"""#379: debrief_max_learner_turns is settings-driven, not hardcoded onto the
constructor default — the DI site must thread it to the constructed
DebriefAnalyzer, mirroring debrief_max_errors's existing wiring.
"""

from app.config import get_settings
from app.features.debrief.dependencies import get_debrief_service


def _analyzer_caps(service):
    analyzer = service._analyzer  # White-box: no public getter.
    return analyzer._max_errors, analyzer._max_learner_turns


def test_wires_the_configured_error_and_learner_turn_caps():
    settings = get_settings()
    service = get_debrief_service(db=None)
    assert _analyzer_caps(service) == (
        settings.debrief_max_errors,
        settings.debrief_max_learner_turns,
    )


def test_a_changed_learner_turn_cap_setting_reaches_the_analyzer(monkeypatch):
    # Proves genuine wiring, not a coincidental match with the default.
    settings = get_settings()
    monkeypatch.setattr(settings, "debrief_max_learner_turns", 7)
    service = get_debrief_service(db=None)
    assert service._analyzer._max_learner_turns == 7
