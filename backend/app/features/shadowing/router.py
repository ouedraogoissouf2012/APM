import base64

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.http.multipart import parse_bounded_multipart
from app.core.llm.interfaces import TtsProvider
from app.core.rate_limit import RateLimiter, user_rate_limit_key
from app.database import get_db, release_request_connection
from app.domain.exceptions import AuthorizationError, ValidationError
from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.conversation.dependencies import get_tts_provider
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
from app.features.voice_consent.dependencies import get_voice_consent_service
from app.features.voice_consent.service import VoiceConsentService

router = APIRouter(tags=["shadowing"])


@router.post("/tts", response_model=TtsOut)
async def synthesize(
    payload: TtsIn,
    request: Request,
    current_user: User = Depends(get_current_user),
    limiter: RateLimiter = Depends(get_shadowing_rate_limiter),
    tts: TtsProvider = Depends(get_tts_provider),
    db: AsyncSession = Depends(get_db),
) -> TtsOut:
    """Synthesize a single phrase to neural audio (the shadowing model voice).
    404 when TTS_ENGINE=device (the client uses its on-device voice instead)."""
    await limiter.check(user_rate_limit_key("tts", current_user.id))
    # #415: auth is done; nothing below touches the DB. Release before Edge TTS.
    await release_request_connection(db)
    audio = await tts.synthesize(payload.text)
    return TtsOut(audio=base64.b64encode(audio).decode("ascii"), mime="audio/mpeg")


@router.post("/shadowing/phrase", response_model=PhraseOut)
async def generate_phrase(
    request: Request,
    current_user: User = Depends(get_current_user),
    limiter: RateLimiter = Depends(get_shadowing_rate_limiter),
    service: ShadowingService = Depends(get_shadowing_service),
    db: AsyncSession = Depends(get_db),
) -> PhraseOut:
    await limiter.check(user_rate_limit_key("shadowing-phrase", current_user.id))
    # #415: cefr_level is already loaded; release before the phrase LLM.
    await release_request_connection(db)
    phrase = await service.generate_phrase(current_user.cefr_level)
    return PhraseOut(text=phrase.text, focus=phrase.focus, tip=phrase.tip)


@router.post("/shadowing/attempt", response_model=AttemptOut)
async def score_attempt(
    request: Request,
    current_user: User = Depends(get_current_user),
    limiter: RateLimiter = Depends(get_shadowing_rate_limiter),
    service: ShadowingService = Depends(get_shadowing_service_with_stt),
    consent: VoiceConsentService = Depends(get_voice_consent_service),
    db: AsyncSession = Depends(get_db),
) -> AttemptOut:
    """Transcribe the learner's recording, diff it against the target phrase, and
    coach the missed words. The audio is used then discarded (never stored)."""
    await limiter.check(user_rate_limit_key("shadowing-attempt", current_user.id))
    # #419: refuse BEFORE parsing the multipart body so revoked transcription
    # consent never lets the audio be read. GOP is opt-in (`scoring`); word-diff
    # still runs when scoring is off.
    allow_transcribe, allow_score = await consent.transcription_and_scoring(current_user.id)
    if not allow_transcribe:
        raise AuthorizationError("Transcription consent has been revoked")
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
        raise ValidationError("Missing 'target_text' field")
    # #328: parse_bounded_multipart bounds the AUDIO part but not text fields — an
    # unbounded target_text would block the event loop in the sync word-diff below
    # (target.split() over megabytes of text), amplify into the GOP call, and be
    # injected into the coaching LLM prompt. Same bound CoachIn.target_text uses
    # for the SAME string on the follow-up /shadowing/coach call.
    if len(target_text) > MAX_TARGET_TEXT_CHARS:
        raise ValidationError(f"'target_text' must be at most {MAX_TARGET_TEXT_CHARS} characters")
    # #415: every DB read is done (auth + consent). Release before STT + GOP —
    # the same idle-hold /transcribe closed for #399. Nothing below touches the DB.
    await release_request_connection(db)
    result = await service.score_attempt(
        target=target_text,
        audio=data,
        native_language=current_user.native_language,
        score_phonemes=allow_score,
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
    db: AsyncSession = Depends(get_db),
) -> CoachOut:
    """Coaching tip on a scored attempt's missed words. Called AFTER /shadowing/attempt
    so the slow coaching LLM never blocks the reactive score display. Does not need
    STT (uses the phrase-only service)."""
    await limiter.check(user_rate_limit_key("shadowing-coach", current_user.id))
    # #415: native_language is already loaded; release before the coaching LLM.
    await release_request_connection(db)
    text = await service.coach_attempt(
        target=payload.target_text,
        missed_words=payload.missed_words,
        native_language=current_user.native_language,
    )
    return CoachOut(coaching=text)
