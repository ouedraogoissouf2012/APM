from pydantic import BaseModel, Field


class PhraseOut(BaseModel):
    text: str
    focus: str
    tip: str


class WordOut(BaseModel):
    target: str
    heard: bool


class AttemptOut(BaseModel):
    transcript: str
    words: list[WordOut]
    missed_words: list[str]
    coaching: str


class TtsIn(BaseModel):
    """Text to synthesize for a shadowing model voice. Bounded so a huge payload
    cannot blow up synthesis time/cost."""

    text: str = Field(min_length=1, max_length=300)


class TtsOut(BaseModel):
    audio: str  # base64-encoded MP3
    mime: str
