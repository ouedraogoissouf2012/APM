"""Speech-to-text providers.

"groq" transcribes the learner's recorded audio with Whisper via Groq's
OpenAI-compatible API (a free API key, no card). Recording happens on the
device; transcription happens server-side so the key stays secret and the
result is far more accurate on a non-native accent than the browser recognizer.
"""

from functools import lru_cache
from typing import Any

from app.core.http_lifecycle import register_closeable
from app.domain.exceptions import LlmProviderError
from app.features.conversation.providers.interfaces import (
    TranscriptWord,
    VerboseTranscript,
)

# Without an explicit timeout/max_retries, the openai SDK's defaults apply — a
# ~600s connect timeout and up to 2 silent retries — on the critical path the
# learner is waiting on for a reply (#230). Bounded here (contained to this
# file, no config.py change); injectable for tests.
_STT_TIMEOUT_SECONDS = 15.0
_STT_MAX_RETRIES = 1


class GroqSttProvider:
    """Whisper transcription via Groq. Language is pinned to English: the
    learner is practising English (imperfectly), so we must not let Whisper
    auto-detect and transcribe their French."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        prompt: str = "",
        timeout_seconds: float = _STT_TIMEOUT_SECONDS,
        max_retries: int = _STT_MAX_RETRIES,
    ) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )
        self._model = model
        # Context prompt biasing decoding toward plausible everyday words; empty
        # to disable. Passed to every request so behaviour is consistent.
        self._prompt = prompt

    def _extra(self) -> dict[str, Any]:
        # temperature=0 makes transcription deterministic — no sampling that can
        # invent an unrelated word on an unclear non-native accent. The prompt is
        # only sent when configured (Whisper treats an empty prompt as none).
        extra: dict[str, Any] = {"temperature": 0}
        if self._prompt:
            extra["prompt"] = self._prompt
        return extra

    async def transcribe(self, audio: bytes) -> str:
        try:
            result = await self._client.audio.transcriptions.create(
                model=self._model,
                file=("speech.wav", audio),
                language="en",
                response_format="json",
                **self._extra(),
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
                **self._extra(),
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

    async def aclose(self) -> None:
        """Close the underlying OpenAI client's connection pool at process
        shutdown (app.core.http_lifecycle). `AsyncOpenAI` exposes an async
        `close()` (not httpx's `aclose()`)."""
        await self._client.close()


def _as_dict(word: Any) -> dict[str, Any]:
    if isinstance(word, dict):
        return word
    # openai SDK returns pydantic-ish objects; fall back to attribute access.
    return {"word": getattr(word, "word", ""), "probability": getattr(word, "probability", None)}


def _prob(word: dict[str, Any]) -> float | None:
    value = word.get("probability")
    return float(value) if isinstance(value, (int, float)) else None


def build_stt_provider(
    engine: str, api_key: str, base_url: str, model: str, prompt: str = ""
) -> Any | None:
    """The server-side STT for the configured engine, or None for "device"
    (the client uses on-device recognition and never calls /transcribe)."""
    if engine == "groq":
        if not api_key.strip():
            raise LlmProviderError("GROQ_API_KEY is required when STT_ENGINE=groq")
        return register_closeable(
            GroqSttProvider(api_key=api_key, base_url=base_url, model=model, prompt=prompt)
        )
    return None


# Process-wide cache: ONE Groq client (one connection pool with keep-alive) per
# configuration, instead of a new client — and a fresh TCP+TLS handshake, plus a
# possible ~1 s cold DNS lookup — on EVERY /transcribe call. Measured: reusing the
# client cuts transcription latency roughly in half (e.g. ~1.5 s -> ~0.7 s), a
# direct win on the latency the learner waits through before the reply starts.
# Errors (missing key) aren't cached — lru_cache only stores successful results.
shared_stt_provider = lru_cache(maxsize=4)(build_stt_provider)
