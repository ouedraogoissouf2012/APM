"""#379: the transcript/history caps are settings-driven, not hardcoded onto
the constructor default — the DI site must actually thread them through. The
constructor already accepted transcript_max_messages (#364/#376); only the
wiring at get_conversation_turn_service was missing, leaving the cap stuck at
200 regardless of config.
"""

from app.config import get_settings
from app.features.conversation.dependencies import get_conversation_turn_service


def _caps(service):
    # White-box: the caps live on private attributes with no public getter
    # (mirrors test_mission_dependencies.py's _llm() helper).
    return service._history_max_messages, service._transcript_max_messages


def test_wires_the_configured_history_and_transcript_caps():
    settings = get_settings()
    service = get_conversation_turn_service(db=None)
    assert _caps(service) == (
        settings.conversation_history_max_messages,
        settings.conversation_transcript_max_messages,
    )


def test_a_changed_transcript_cap_setting_reaches_the_service(monkeypatch):
    # Proves genuine wiring, not a coincidental match with the default: a
    # DISTINCTIVE overridden value must reach the constructed service.
    settings = get_settings()
    monkeypatch.setattr(settings, "conversation_transcript_max_messages", 42)
    service = get_conversation_turn_service(db=None)
    assert service._transcript_max_messages == 42


def test_a_changed_history_cap_setting_reaches_the_service(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "conversation_history_max_messages", 3)
    service = get_conversation_turn_service(db=None)
    assert service._history_max_messages == 3
