import base64

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import get_settings
from app.core.rate_limit import RateLimiter, user_rate_limit_key
from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.conversation.audio_upload import parse_bounded_multipart
from app.features.conversation.dependencies import get_tts_provider
from app.features.conversation.providers.interfaces import TtsProvider
from app.features.shadowing.dependencies import (
    get_shadowing_rate_limiter,
    get_shadowing_service,
    get_shadowing_service_with_stt,
)
from app.features.shadowing.schemas import (
    MAX_TARGET_TEXT_CHARS,
    AttemptOut,
    CoachIn,
    CoachOut,
    PhonemeOut,
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
    await limiter.check(user_rate_limit_key("tts", current_user.id))
    audio = await tts.synthesize(payload.text)
    return TtsOut(audio=base64.b64encode(audio).decode("ascii"), mime="audio/mpeg")


@router.post("/shadowing/phrase", response_model=PhraseOut)
async def generate_phrase(
    request: Request,
    current_user: User = Depends(get_current_user),
    limiter: RateLimiter = Depends(get_shadowing_rate_limiter),
    service: ShadowingService = Depends(get_shadowing_service),
) -> PhraseOut:
    await limiter.check(user_rate_limit_key("shadowing-phrase", current_user.id))
    phrase = await service.generate_phrase(current_user.cefr_level)
    return PhraseOut(text=phrase.text, focus=phrase.focus, tip=phrase.tip)


@router.post("/shadowing/attempt", response_model=AttemptOut)
async def score_attempt(
    request: Request,
    current_user: User = Depends(get_current_user),
    limiter: RateLimiter = Depends(get_shadowing_rate_limiter),
    service: ShadowingService = Depends(get_shadowing_service_with_stt),
) -> AttemptOut:
    """Transcribe the learner's recording, diff it against the target phrase, and
    coach the missed words. The audio is used then discarded (never stored)."""
    await limiter.check(user_rate_limit_key("shadowing-attempt", current_user.id))
    settings = get_settings()
    # Bounded, in-memory upload (#230): a plain `UploadFile` parameter goes
    # through Starlette's default parser, which spools past 1 MB and enforces no
    # size cap at all — the same gap /transcribe closed for #120/#227.
    data, fields = await parse_bounded_multipart(
        request,
        max_bytes=settings.max_upload_bytes,
        spool_max_size=settings.max_request_body_bytes,
    )
    target_text = fields.get("target_text")
    if not target_text:
        raise HTTPException(status_code=422, detail="Missing 'target_text' field")
    # #328: parse_bounded_multipart bounds the AUDIO part but not text fields — an
    # unbounded target_text would block the event loop in the sync word-diff below
    # (target.split() over megabytes of text), amplify into the GOP call, and be
    # injected into the coaching LLM prompt. Same bound CoachIn.target_text uses
    # for the SAME string on the follow-up /shadowing/coach call.
    if len(target_text) > MAX_TARGET_TEXT_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"'target_text' must be at most {MAX_TARGET_TEXT_CHARS} characters",
        )
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
        phonemes=[PhonemeOut(phoneme=p.phoneme, score=p.score) for p in result.phonemes],
    )


@router.post("/shadowing/coach", response_model=CoachOut)
async def coach_attempt(
    payload: CoachIn,
    request: Request,
    current_user: User = Depends(get_current_user),
    limiter: RateLimiter = Depends(get_shadowing_rate_limiter),
    service: ShadowingService = Depends(get_shadowing_service),
) -> CoachOut:
    """Coaching tip on a scored attempt's missed words. Called AFTER /shadowing/attempt
    so the slow coaching LLM never blocks the reactive score display. Does not need
    STT (uses the phrase-only service)."""
    await limiter.check(user_rate_limit_key("shadowing-coach", current_user.id))
    text = await service.coach_attempt(
        target=payload.target_text,
        missed_words=payload.missed_words,
        native_language=current_user.native_language,
    )
    return CoachOut(coaching=text)
