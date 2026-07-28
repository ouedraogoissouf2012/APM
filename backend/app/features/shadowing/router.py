import base64

from fastapi import APIRouter, Depends, Form, Request, UploadFile

from app.core.rate_limit import RateLimiter
from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.conversation.dependencies import get_tts_provider
from app.features.conversation.providers.interfaces import TtsProvider
from app.features.shadowing.dependencies import (
    get_shadowing_rate_limiter,
    get_shadowing_service,
    get_shadowing_service_with_stt,
)
from app.features.shadowing.schemas import (
    AttemptOut,
    PhraseOut,
    TtsIn,
    TtsOut,
    WordOut,
)
from app.features.shadowing.service import ShadowingService

router = APIRouter(tags=["shadowing"])


@router.post("/tts", response_model=TtsOut)
async def synthesize(
    payload: TtsIn,
    request: Request,
    current_user: User = Depends(get_current_user),
    limiter: RateLimiter = Depends(get_shadowing_rate_limiter),
    tts: TtsProvider = Depends(get_tts_provider),
) -> TtsOut:
    """Synthesize a single phrase to neural audio (the shadowing model voice).
    404 when TTS_ENGINE=device (the client uses its on-device voice instead)."""
    client_host = request.client.host if request.client else "anonymous"
    await limiter.check(f"tts:{client_host}:user:{current_user.id}")
    audio = await tts.synthesize(payload.text)
    return TtsOut(audio=base64.b64encode(audio).decode("ascii"), mime="audio/mpeg")


@router.post("/shadowing/phrase", response_model=PhraseOut)
async def generate_phrase(
    request: Request,
    current_user: User = Depends(get_current_user),
    limiter: RateLimiter = Depends(get_shadowing_rate_limiter),
    service: ShadowingService = Depends(get_shadowing_service),
) -> PhraseOut:
    client_host = request.client.host if request.client else "anonymous"
    await limiter.check(f"shadowing-phrase:{client_host}:user:{current_user.id}")
    phrase = await service.generate_phrase(current_user.cefr_level)
    return PhraseOut(text=phrase.text, focus=phrase.focus, tip=phrase.tip)


@router.post("/shadowing/attempt", response_model=AttemptOut)
async def score_attempt(
    request: Request,
    audio: UploadFile,
    target_text: str = Form(...),
    current_user: User = Depends(get_current_user),
    limiter: RateLimiter = Depends(get_shadowing_rate_limiter),
    service: ShadowingService = Depends(get_shadowing_service_with_stt),
) -> AttemptOut:
    """Transcribe the learner's recording, diff it against the target phrase, and
    coach the missed words. The audio is used then discarded (never stored)."""
    client_host = request.client.host if request.client else "anonymous"
    await limiter.check(f"shadowing-attempt:{client_host}:user:{current_user.id}")
    data = await audio.read()
    result = await service.score_attempt(
        target=target_text, audio=data, native_language=current_user.native_language
    )
    return AttemptOut(
        transcript=result.transcript,
        words=[
            WordOut(target=w.target, heard=w.heard, score=w.score, confidence=w.confidence)
            for w in result.words
        ],
        missed_words=result.missed_words,
        coaching=result.coaching,
    )
