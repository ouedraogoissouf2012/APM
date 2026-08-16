from datetime import datetime

from pydantic import BaseModel, Field


class TurnIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    # Offline replay (#431): when the learner actually spoke. Ignored if
    # missing, in the future, or older than 48h (see clamp_practiced_at).
    practiced_at: datetime | None = None


class TurnOut(BaseModel):
    reply: str
