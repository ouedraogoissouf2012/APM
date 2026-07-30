"""Shadowing use cases: generate a target phrase, and score a spoken attempt.

An attempt is scored by transcribing the recorded audio (reusing the STT
provider), diffing the transcript against the target (pure logic), and coaching
the missed words. When a pronunciation engine is configured (#111 step 2), a
phoneme-level GOP score is also fetched, in parallel, as a finer complement.
Nothing is persisted — the audio never touches the database (privacy by default;
see #128).
"""

import asyncio
import logging

from app.domain.exceptions import LlmProviderError
from app.features.conversation.providers.interfaces import SttProvider
from app.features.pronunciation.domain import PhonemeScore
from app.features.pronunciation.provider import PronunciationProvider
from app.features.pronunciation.scorer import score_words
from app.features.shadowing.coach import ShadowingCoach
from app.features.shadowing.diff import compare_words, missed_words
from app.features.shadowing.domain import AttemptResult, ShadowingPhrase, WordComparison
from app.features.shadowing.generator import PhraseGenerator

logger = logging.getLogger(__name__)


class ShadowingService:
    def __init__(
        self,
        generator: PhraseGenerator,
        coach: ShadowingCoach,
        stt: SttProvider | None = None,
        pronunciation: PronunciationProvider | None = None,
    ) -> None:
        # `stt` is only needed to score an attempt; generating a phrase does not
        # require it, so it stays optional and generating never depends on STT.
        # `pronunciation` is the optional GOP engine — absent by default.
        self._generator = generator
        self._coach = coach
        self._stt = stt
        self._pronunciation = pronunciation

    async def generate_phrase(self, cefr_level: str) -> ShadowingPhrase:
        return await self._generator.generate(cefr_level)

    async def score_attempt(self, target: str, audio: bytes, native_language: str) -> AttemptResult:
        if self._stt is None:
            raise RuntimeError("Scoring an attempt requires a speech-to-text provider")
        if not audio:
            return AttemptResult(transcript="", words=[], missed_words=[], coaching="")

        # Fetch the phoneme-level GOP score alongside transcription: they are
        # independent calls, so run them concurrently rather than in sequence.
        verbose, phonemes = await asyncio.gather(
            self._stt.transcribe_verbose(audio),
            self._score_phonemes(target, audio),
        )

        # One verbose call gives us both the text (for the heard/missed diff) and
        # per-word confidence (for the clarity score).
        heard = compare_words(target, verbose.text)
        scores = score_words(target, verbose)
        comparisons = _merge(heard, scores)
        missed = missed_words(heard)
        # Coaching (a slow LLM call, 3-8 s) is intentionally NOT done here: scoring
        # must return fast so the UI shows the colored words + phonemes immediately.
        # The client fetches coaching afterwards via coach_attempt (using the
        # missed_words returned here), so the slow call never blocks the display.
        return AttemptResult(
            transcript=verbose.text,
            words=comparisons,
            missed_words=missed,
            coaching="",
            phonemes=phonemes,
        )

    async def coach_attempt(
        self, target: str, missed_words: list[str], native_language: str
    ) -> str:
        """Short coaching tip on the missed words. A separate, deferred call so the
        slow coaching LLM never blocks the reactive score display."""
        return await self._coach.coach(target, missed_words, native_language)

    async def _score_phonemes(self, target: str, audio: bytes) -> list[PhonemeScore]:
        """GOP scores when an engine is configured, else empty. A provider failure
        degrades gracefully: the attempt still succeeds on the word-level signal —
        phoneme scoring is a complement, never a hard dependency."""
        if self._pronunciation is None:
            return []
        try:
            return await self._pronunciation.score_phonemes(audio=audio, target_text=target)
        except LlmProviderError:
            logger.warning("Pronunciation scoring failed; returning attempt without phonemes")
            return []


def _merge(heard: list[WordComparison], scores: list) -> list[WordComparison]:
    """Attach each word's clarity score to its heard/missed verdict. Both lists
    derive from the same target phrase, so they align one-to-one by position."""
    by_position = list(zip(heard, scores, strict=False))
    return [
        WordComparison(
            target=h.target,
            heard=h.heard,
            score=s.score,
            confidence=s.confidence,
        )
        for h, s in by_position
    ]
