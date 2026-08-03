"""LLM engine names, shared by settings, factories and DI wiring.

Single source of truth so a typo in an env var (e.g. VOICE_ENGINE=deepsek)
fails loudly at startup instead of silently degrading to the fake engine.
"""

from typing import Literal

ENGINE_FAKE = "fake"
ENGINE_DEEPSEEK = "deepseek"
# Groq's OpenAI-compatible LLM API (Llama 3.3). Far lower time-to-first-token
# (~0.4 s vs ~2-4 s for DeepSeek), so it drives the live conversation turn faster.
ENGINE_GROQ = "groq"

# Only implemented engines are valid config values. A "livekit" realtime
# engine (issue #69) must be added here the day it actually exists — until
# then, configuring it fails at startup instead of 502-ing on every turn.
VoiceEngineName = Literal["fake", "deepseek", "groq"]
DebriefEngineName = Literal["fake", "deepseek"]
MissionEngineName = Literal["fake", "deepseek"]
ShadowingEngineName = Literal["fake", "deepseek"]

# Pronunciation (#111 step 2): "fake" makes no phonetic claim (default, no extra
# service); "gop" calls the wav2vec2 pronunciation microservice over HTTP.
ENGINE_GOP = "gop"
PronunciationEngineName = Literal["fake", "gop"]
