"""Shadowing use cases: generate a target phrase, and score a spoken attempt.

An attempt is scored by transcribing the recorded audio (reusing the STT
provider), diffing the transcript against the target (pure logic), and coaching
the missed words. Nothing is persisted — the audio never touches the database
(privacy by default; see #128).
"""

from app.features.conversation.providers.interfaces import SttProvider
from app.features.pronunciation.scorer import score_words
from app.features.shadowing.coach import ShadowingCoach
from app.features.shadowing.diff import compare_words, missed_words
from app.features.shadowing.domain import AttemptResult, ShadowingPhrase, WordComparison
from app.features.shadowing.generator import PhraseGenerator


class ShadowingService:
    def __init__(
        self,
        generator: PhraseGenerator,
        coach: ShadowingCoach,
        stt: SttProvider | None = None,
    ) -> None:
        # `stt` is only needed to score an attempt; generating a phrase does not
        # require it, so it stays optional and generating never depends on STT.
        self._generator = generator
        self._coach = coach
        self._stt = stt

    async def generate_phrase(self, cefr_level: str) -> ShadowingPhrase:
        return await self._generator.generate(cefr_level)

    async def score_attempt(self, target: str, audio: bytes, native_language: str) -> AttemptResult:
        if self._stt is None:
            raise RuntimeError("Scoring an attempt requires a speech-to-text provider")
        if not audio:
            return AttemptResult(transcript="", words=[], missed_words=[], coaching="")

        # One verbose call gives us both the text (for the heard/missed diff) and
        # per-word confidence (for the clarity score).
        verbose = await self._stt.transcribe_verbose(audio)
        heard = compare_words(target, verbose.text)
        scores = score_words(target, verbose)
        comparisons = _merge(heard, scores)
        missed = missed_words(heard)
        coaching = await self._coach.coach(target, missed, native_language)
        return AttemptResult(
            transcript=verbose.text,
            words=comparisons,
            missed_words=missed,
            coaching=coaching,
        )


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
