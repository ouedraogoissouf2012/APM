from typing import Literal

from pydantic import BaseModel


class VocabularyEntryOut(BaseModel):
    id: int
    session_id: int | None
    word: str
    phonetic: str
    translation: str
    example: str
    status: str

    model_config = {"from_attributes": True}


class StatusUpdate(BaseModel):
    # Mirrors STATUS_REVIEW / STATUS_KNOWN in models.py; kept as literals so the
    # API validates the closed set (a bad value is a 422, not a silent write).
    status: Literal["review", "known"]
