from pydantic import BaseModel, Field

# Shared with router.py's manual bound on the /shadowing/attempt multipart
# `target_text` field (#328) — the same string flows into CoachIn.target_text
# on the follow-up /shadowing/coach call, so both must agree on one bound.
MAX_TARGET_TEXT_CHARS = 300


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


class CoachIn(BaseModel):
    """Ask for coaching on a scored attempt's misses. Sent AFTER the attempt is
    displayed, so the slow coaching LLM never blocks the score UI."""

    target_text: str = Field(min_length=1, max_length=MAX_TARGET_TEXT_CHARS)
    missed_words: list[str] = Field(default_factory=list, max_length=50)


class CoachOut(BaseModel):
    coaching: str


class TtsIn(BaseModel):
    """Text to synthesize for a shadowing model voice. Bounded so a huge payload
    cannot blow up synthesis time/cost."""

    text: str = Field(min_length=1, max_length=300)


class TtsOut(BaseModel):
    audio: str  # base64-encoded MP3
    mime: str
