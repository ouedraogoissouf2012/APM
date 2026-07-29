"""Minimal-pairs use case: score one production attempt at a pair word.

Transcribe the recording, decide whether the learner said the target or the
other word of the pair, and coach the confusion. Nothing is persisted; the audio
never touches the database (privacy by default, cf #128).
"""

from app.features.conversation.providers.interfaces import SttProvider
from app.features.minimal_pairs.coach import PairCoach
from app.features.minimal_pairs.domain import PairAttemptResult
from app.features.minimal_pairs.pair_scoring import score_pair_attempt


class MinimalPairsService:
    def __init__(self, coach: PairCoach, stt: SttProvider) -> None:
        self._coach = coach
        self._stt = stt

    async def score_attempt(
        self, target: str, other: str, audio: bytes, native_language: str
    ) -> PairAttemptResult:
        if not audio:
            return PairAttemptResult(transcript="", said_target=False, said_other=False)

        verbose = await self._stt.transcribe_verbose(audio)
        scored = score_pair_attempt(target=target, other=other, verbose=verbose)

        # Coach only when the target did not come through cleanly.
        coaching = ""
        if not scored.said_target:
            coaching = await self._coach.coach(
                target=target,
                other=other,
                said_other=scored.said_other,
                native_language=native_language,
            )
        return PairAttemptResult(
            transcript=scored.transcript,
            said_target=scored.said_target,
            said_other=scored.said_other,
            coaching=coaching,
        )
