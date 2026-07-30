from pydantic import BaseModel, Field


class PhraseOut(BaseModel):
    text: str
    focus: str
    tip: str


class WordOut(BaseModel):
    target: str
    heard: bool
    # Pronunciation clarity (#111): score 0..1 (null = unknown), confidence 0..1
    # (null = treat as reliable). The mobile map hides scores with low confidence.
    score: float | None = None
    confidence: float | None = None


class PhonemeOut(BaseModel):
    """One expected phoneme and its GOP score (#111 step 2). Empty list when no
    pronunciation engine is configured. The score is a raw acoustic measure — the
    client must present it with uncertainty, not as an absolute verdict."""

    phoneme: str
    score: float


class AttemptOut(BaseModel):
    transcript: str
    words: list[WordOut]
    missed_words: list[str]
    coaching: str
    phonemes: list[PhonemeOut] = []


class TtsIn(BaseModel):
    """Text to synthesize for a shadowing model voice. Bounded so a huge payload
    cannot blow up synthesis time/cost."""

    text: str = Field(min_length=1, max_length=300)


class TtsOut(BaseModel):
    audio: str  # base64-encoded MP3
    mime: str
