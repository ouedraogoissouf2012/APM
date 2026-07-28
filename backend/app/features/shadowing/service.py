"""Shadowing use cases: generate a target phrase, and score a spoken attempt.

An attempt is scored by transcribing the recorded audio (reusing the STT
provider), diffing the transcript against the target (pure logic), and coaching
the missed words. Nothing is persisted — the audio never touches the database
(privacy by default; see #128).
"""

from app.features.conversation.providers.interfaces import SttProvider
from app.features.shadowing.coach import ShadowingCoach
from app.features.shadowing.diff import compare_words, missed_words
from app.features.shadowing.domain import AttemptResult, ShadowingPhrase
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
        transcript = await self._stt.transcribe(audio) if audio else ""
        comparisons = compare_words(target, transcript)
        missed = missed_words(comparisons)
        coaching = await self._coach.coach(target, missed, native_language)
        return AttemptResult(
            transcript=transcript,
            words=comparisons,
            missed_words=missed,
            coaching=coaching,
        )
