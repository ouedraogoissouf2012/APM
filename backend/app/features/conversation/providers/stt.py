"""Speech-to-text providers.

"groq" transcribes the learner's recorded audio with Whisper via Groq's
OpenAI-compatible API (a free API key, no card). Recording happens on the
device; transcription happens server-side so the key stays secret and the
result is far more accurate on a non-native accent than the browser recognizer.
"""

from functools import lru_cache
from typing import Any

from app.domain.exceptions import LlmProviderError
from app.features.conversation.providers.interfaces import (
    TranscriptWord,
    VerboseTranscript,
)


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
                file=("speech.wav", audio),
                language="en",
                response_format="json",
            )
        except Exception as exc:
            raise LlmProviderError("Transcription failed") from exc
        return (result.text or "").strip()

    async def transcribe_verbose(self, audio: bytes) -> VerboseTranscript:
        """verbose_json with word granularity: Whisper returns per-word segments,
        each carrying a `probability` (how confident it was in that word) — our
        pronunciation-clarity signal, at zero extra dependency."""
        try:
            result = await self._client.audio.transcriptions.create(
                model=self._model,
                file=("speech.wav", audio),
                language="en",
                response_format="verbose_json",
                timestamp_granularities=["word"],
            )
        except Exception as exc:
            raise LlmProviderError("Transcription failed") from exc
        text = (getattr(result, "text", "") or "").strip()
        raw_words = getattr(result, "words", None) or []
        words = [
            TranscriptWord(word=str(w.get("word", "")).strip(), probability=_prob(w))
            for w in (_as_dict(rw) for rw in raw_words)
            if str(w.get("word", "")).strip()
        ]
        return VerboseTranscript(text=text, words=words)


def _as_dict(word: Any) -> dict[str, Any]:
    if isinstance(word, dict):
        return word
    # openai SDK returns pydantic-ish objects; fall back to attribute access.
    return {"word": getattr(word, "word", ""), "probability": getattr(word, "probability", None)}


def _prob(word: dict[str, Any]) -> float | None:
    value = word.get("probability")
    return float(value) if isinstance(value, (int, float)) else None


def build_stt_provider(engine: str, api_key: str, base_url: str, model: str) -> Any | None:
    """The server-side STT for the configured engine, or None for "device"
    (the client uses on-device recognition and never calls /transcribe)."""
    if engine == "groq":
        if not api_key.strip():
            raise LlmProviderError("GROQ_API_KEY is required when STT_ENGINE=groq")
        return GroqSttProvider(api_key=api_key, base_url=base_url, model=model)
    return None


# Process-wide cache: ONE Groq client (one connection pool with keep-alive) per
# configuration, instead of a new client — and a fresh TCP+TLS handshake, plus a
# possible ~1 s cold DNS lookup — on EVERY /transcribe call. Measured: reusing the
# client cuts transcription latency roughly in half (e.g. ~1.5 s -> ~0.7 s), a
# direct win on the latency the learner waits through before the reply starts.
# Errors (missing key) aren't cached — lru_cache only stores successful results.
shared_stt_provider = lru_cache(maxsize=4)(build_stt_provider)
