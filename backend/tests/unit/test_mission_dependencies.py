"""The mission DI wires a REAL llm (not the fake) for real engines (#209).

Before the fix only 'deepseek' got a real provider; 'groq'/'groq_fallback' silently
fell back to the fake. Missions now use build_feature_llm like the conversation and
debrief, so the robust Groq->DeepSeek chain works and a dead DeepSeek key alone no
longer breaks missions.
"""

import pytest

from app.config import get_settings
from app.features.missions.dependencies import get_mission_service
from app.features.missions.fake_llm import FakeMissionLlm


def _llm(service):
    # White-box: the compiler holds the injected provider.
    return service._compiler._llm


def test_fake_engine_uses_the_fake_llm():
    # conftest forces MISSION_ENGINE=fake for the whole test run.
    service = get_mission_service(db=None)
    assert isinstance(_llm(service), FakeMissionLlm)


@pytest.mark.parametrize("engine", ["deepseek", "groq", "groq_fallback"])
def test_a_real_engine_uses_a_real_llm_not_the_fake(engine, monkeypatch):
    monkeypatch.setattr(get_settings(), "mission_engine", engine)
    service = get_mission_service(db=None)
    assert not isinstance(_llm(service), FakeMissionLlm)
