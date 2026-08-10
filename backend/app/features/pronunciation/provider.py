"""Pronunciation-scoring providers (#111 step 2 — GOP bridge).

Phoneme-level Goodness-of-Pronunciation is computed by a separate microservice
(wav2vec2, too heavy to embed in this backend). The backend depends on a
`PronunciationProvider` Protocol (DIP); the real implementation is an HTTP client
to that service, and a fake makes the default configuration honest and testable.

Substitutable by design (LSP): the fake and the HTTP client are interchangeable,
so nothing above this layer knows whether a GOP service exists.
"""

from functools import lru_cache
from typing import Any, Protocol

import httpx

from app.core.engines import ENGINE_FAKE, ENGINE_GOP
from app.domain.exceptions import LlmProviderError
from app.features.pronunciation.domain import PhonemeScore


class PronunciationProvider(Protocol):
    """Score how well each expected phoneme of `target_text` was pronounced in
    `audio`. Returns an empty list when no phonetic signal is available (rather
    than inventing scores)."""

    async def score_phonemes(self, audio: bytes, target_text: str) -> list[PhonemeScore]: ...


class FakePronunciationProvider:
    """The honest default: no GOP engine configured -> no phonetic scores.

    Returning [] (never fabricated numbers) means the UI shows nothing rather than
    a made-up verdict — consistent with the other `fake` engines in this backend."""

    async def score_phonemes(self, audio: bytes, target_text: str) -> list[PhonemeScore]:
        return []


class HttpGopProvider:
    """Calls the pronunciation microservice's `POST /score` endpoint.

    The httpx client is injected (DIP) so tests drive it with a mock transport and
    the timeout/base_url are configured once at wiring time. Any transport or HTTP
    error is wrapped in the domain's LlmProviderError, so callers handle a single
    failure type regardless of the underlying engine."""

    def __init__(self, client: httpx.AsyncClient, base_url: str, secret: str = "") -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        # Shared-secret auth (#231): the microservice rejects /score without this
        # header once it is configured with a matching secret. Empty -> header
        # omitted, matching the service's own "unconfigured -> no-op" default.
        self._headers = {"X-Internal-Secret": secret} if secret else {}

    async def score_phonemes(self, audio: bytes, target_text: str) -> list[PhonemeScore]:
        # No audio -> nothing to score. Skip the network entirely.
        if not audio:
            return []
        try:
            response = await self._client.post(
                f"{self._base_url}/score",
                files={"audio": ("speech.wav", audio, "audio/wav")},
                data={"target_text": target_text},
                headers=self._headers,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # httpx.HTTPError covers transport + status errors; ValueError covers
            # a non-JSON body. Either way the engine failed to produce a score.
            raise LlmProviderError("Pronunciation scoring failed") from exc
        return _parse_phonemes(payload)


def build_pronunciation_provider(
    engine: str, service_url: str, timeout_seconds: float, secret: str = ""
) -> PronunciationProvider:
    """Select the pronunciation provider from config.

    Unknown engines raise instead of silently degrading — settings validate the
    engine names (Literal), this is defense in depth."""
    if engine == ENGINE_FAKE:
        return FakePronunciationProvider()
    if engine == ENGINE_GOP:
        client = httpx.AsyncClient(timeout=timeout_seconds)
        return HttpGopProvider(client=client, base_url=service_url, secret=secret)
    raise LlmProviderError(f"Unsupported pronunciation engine: {engine!r}")


# Process-wide cache: one AsyncClient (one connection pool) per configuration,
# instead of a new client per HTTP request.
shared_pronunciation_provider = lru_cache(maxsize=4)(build_pronunciation_provider)


def _parse_phonemes(payload: Any) -> list[PhonemeScore]:
    """Defensively read the microservice response. An entry missing its phoneme or
    score is dropped rather than crashing the whole attempt."""
    raw = payload.get("phonemes", []) if isinstance(payload, dict) else []
    scores: list[PhonemeScore] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        phoneme = entry.get("phoneme")
        score = entry.get("score")
        if isinstance(phoneme, str) and isinstance(score, (int, float)):
            scores.append(PhonemeScore(phoneme=phoneme, score=float(score)))
    return scores
