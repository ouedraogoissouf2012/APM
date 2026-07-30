"""Unit tests for ShadowingService.score_attempt orchestration (#111 step 2).

Focus on the pronunciation-provider wiring: the phoneme-level GOP scores are a
COMPLEMENT to the word-level result, computed alongside it. Crucially, a failing
GOP provider must NOT break the attempt — the word-level scoring still stands.
"""

import pytest

from app.domain.exceptions import LlmProviderError
from app.features.conversation.providers.interfaces import (
    TranscriptWord,
    VerboseTranscript,
)
from app.features.pronunciation.domain import PhonemeScore
from app.features.shadowing.service import ShadowingService


class _FakeStt:
    def __init__(self, transcript: str, prob: float = 0.9) -> None:
        self._transcript = transcript
        self._prob = prob

    async def transcribe(self, audio: bytes) -> str:
        return self._transcript

    async def transcribe_verbose(self, audio: bytes) -> VerboseTranscript:
        words = [TranscriptWord(w, self._prob) for w in self._transcript.split()]
        return VerboseTranscript(text=self._transcript, words=words)


class _NoCoach:
    async def coach(self, target, missed, native_language) -> str:
        return ""


class _StubPron:
    """A pronunciation provider that returns scripted phonemes and records calls."""

    def __init__(self, phonemes: list[PhonemeScore]) -> None:
        self._phonemes = phonemes
        self.calls: list[tuple[bytes, str]] = []

    async def score_phonemes(self, audio: bytes, target_text: str) -> list[PhonemeScore]:
        self.calls.append((audio, target_text))
        return self._phonemes


class _FailingPron:
    async def score_phonemes(self, audio: bytes, target_text: str) -> list[PhonemeScore]:
        raise LlmProviderError("gop service down")


def _service(stt, pron=None) -> ShadowingService:
    return ShadowingService(
        generator=None,  # not used by score_attempt
        coach=_NoCoach(),
        stt=stt,
        pronunciation=pron,
    )


@pytest.mark.asyncio
async def test_attempt_includes_phoneme_scores_from_provider():
    pron = _StubPron([PhonemeScore(phoneme="θ", score=0.08), PhonemeScore(phoneme="k", score=0.9)])
    result = await _service(_FakeStt("think"), pron).score_attempt(
        target="think", audio=b"WAV", native_language="fr"
    )
    assert result.phonemes == [
        PhonemeScore(phoneme="θ", score=0.08),
        PhonemeScore(phoneme="k", score=0.9),
    ]
    # The provider was called with the raw audio and the target text.
    assert pron.calls == [(b"WAV", "think")]


@pytest.mark.asyncio
async def test_attempt_without_provider_has_no_phonemes_but_still_scores_words():
    # Default (fake / no provider): word-level result intact, phonemes empty.
    result = await _service(_FakeStt("think"), pron=None).score_attempt(
        target="think", audio=b"WAV", native_language="fr"
    )
    assert result.phonemes == []
    assert result.transcript == "think"
    assert [w.target for w in result.words] == ["think"]


@pytest.mark.asyncio
async def test_provider_failure_degrades_gracefully_without_breaking_attempt():
    # The GOP service is down -> the attempt STILL succeeds (word-level scoring is
    # the primary signal); phonemes are simply empty. GOP is a complement, not a
    # hard dependency.
    result = await _service(_FakeStt("think"), _FailingPron()).score_attempt(
        target="think", audio=b"WAV", native_language="fr"
    )
    assert result.phonemes == []
    assert result.transcript == "think"
    assert result.words  # word-level scoring unaffected


@pytest.mark.asyncio
async def test_empty_audio_returns_empty_result_and_skips_provider():
    pron = _StubPron([PhonemeScore(phoneme="θ", score=0.5)])
    result = await _service(_FakeStt("think"), pron).score_attempt(
        target="think", audio=b"", native_language="fr"
    )
    assert result.phonemes == []
    assert result.words == []
    assert pron.calls == []  # no audio -> provider never called
