from pydantic import BaseModel


class PairAttemptOut(BaseModel):
    transcript: str
    said_target: bool
    said_other: bool
    coaching: str
