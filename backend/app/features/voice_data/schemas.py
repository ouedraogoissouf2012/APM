from pydantic import BaseModel


class VoiceDataExportOut(BaseModel):
    # Explicit and honest: raw recordings are never kept server-side.
    raw_audio_retained: bool
    utterances: list[dict]
    vocabulary: list[dict]
    debriefs: list[dict]
    review_items: list[dict]


class VoiceDataEraseOut(BaseModel):
    # Counts of what was actually deleted, per kind (0 when there was nothing).
    deleted: dict[str, int]
