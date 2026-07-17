"""LLM engine names, shared by settings, factories and DI wiring.

Single source of truth so a typo in an env var (e.g. VOICE_ENGINE=deepsek)
fails loudly at startup instead of silently degrading to the fake engine.
"""

from typing import Literal

ENGINE_FAKE = "fake"
ENGINE_DEEPSEEK = "deepseek"
ENGINE_LIVEKIT = "livekit"

VoiceEngineName = Literal["fake", "deepseek", "livekit"]
DebriefEngineName = Literal["fake", "deepseek"]
