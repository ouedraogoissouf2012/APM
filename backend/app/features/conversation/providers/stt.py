"""Speech-to-text providers.

"groq" transcribes the learner's recorded audio with Whisper via Groq's
OpenAI-compatible API (a free API key, no card). Recording happens on the
device; transcription happens server-side so the key stays secret and the
result is far more accurate on a non-native accent than the browser recognizer.
"""

from typing import Any

from app.domain.exceptions import LlmProviderError


class GroqSttProvider:
    """Whisper transcription via Groq. Language is pinned to English: the
    learner is practising English (imperfectly), so we must not let Whisper
    auto-detect and transcribe their French."""

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    async def transcribe(self, audio: bytes) -> str:
        try:
            result = await self._client.audio.transcriptions.create(
                model=self._model,
                file=("speech.webm", audio),
                language="en",
                response_format="json",
            )
        except Exception as exc:
            raise LlmProviderError("Transcription failed") from exc
        return (result.text or "").strip()


def build_stt_provider(engine: str, api_key: str, base_url: str, model: str) -> Any | None:
    """The server-side STT for the configured engine, or None for "device"
    (the client uses on-device recognition and never calls /transcribe)."""
    if engine == "groq":
        if not api_key.strip():
            raise LlmProviderError("GROQ_API_KEY is required when STT_ENGINE=groq")
        return GroqSttProvider(api_key=api_key, base_url=base_url, model=model)
    return None
