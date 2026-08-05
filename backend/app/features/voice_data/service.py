"""Export & erasure of a learner's voice-derived data (#128).

Raw audio is never stored (the /transcribe upload is processed in memory then
discarded). What persists and is derived from the learner's voice is: their
transcribed utterances, the debrief analysis of them, the captured vocabulary
(their real sentences), and the recurring-error review items. This service lets
the learner EXPORT that footprint (data portability) and ERASE it.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class VoiceDataExport:
    # A note that raw audio is never retained, so the export is honest about scope.
    raw_audio_retained: bool
    utterances: list[dict]  # [{session_id, started_at, text}]
    vocabulary: list[dict]  # [{word, translation, example}]


class VoiceDataSource(Protocol):
    async def utterances(self, user_id: int) -> list[dict]: ...

    async def vocabulary(self, user_id: int) -> list[dict]: ...

    async def purge(self, user_id: int) -> dict[str, int]:
        """Delete all voice-derived rows for the user; return counts per kind."""
        ...


class VoiceDataService:
    def __init__(self, source: VoiceDataSource) -> None:
        self._source = source

    async def export(self, user_id: int) -> VoiceDataExport:
        return VoiceDataExport(
            raw_audio_retained=False,  # never stored — see /transcribe
            utterances=await self._source.utterances(user_id),
            vocabulary=await self._source.vocabulary(user_id),
        )

    async def erase(self, user_id: int) -> dict[str, int]:
        """Erase the learner's voice-derived data. Returns counts per kind so the
        UI can honestly report what was deleted (0s when there was nothing)."""
        return await self._source.purge(user_id)
