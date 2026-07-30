from pydantic import BaseModel


class PhonemeScoreOut(BaseModel):
    phoneme: str
    score: float
    start: int
    end: int


class ScoreOut(BaseModel):
    phonemes: list[PhonemeScoreOut]
