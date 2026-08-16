from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.http.multipart import parse_bounded_multipart
from app.core.rate_limit import RateLimiter, user_rate_limit_key
from app.database import get_db, release_request_connection
from app.domain.exceptions import AuthorizationError, ValidationError
from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.minimal_pairs.dependencies import (
    get_minimal_pairs_rate_limiter,
    get_minimal_pairs_service,
)
from app.features.minimal_pairs.schemas import MAX_WORD_CHARS, PairAttemptOut
from app.features.minimal_pairs.service import MinimalPairsService
from app.features.voice_consent.dependencies import get_voice_consent_service
from app.features.voice_consent.service import VoiceConsentService

router = APIRouter(prefix="/minimal-pairs", tags=["minimal-pairs"])


@router.post("/attempt", response_model=PairAttemptOut)
async def score_attempt(
    request: Request,
    current_user: User = Depends(get_current_user),
    limiter: RateLimiter = Depends(get_minimal_pairs_rate_limiter),
    service: MinimalPairsService = Depends(get_minimal_pairs_service),
    consent: VoiceConsentService = Depends(get_voice_consent_service),
    db: AsyncSession = Depends(get_db),
) -> PairAttemptOut:
    """Score a spoken minimal-pair attempt: did the learner say the target word,
    or the other (confused) word of the pair? The audio is used then discarded."""
    await limiter.check(user_rate_limit_key("minimal-pairs", current_user.id))
    # #419: same gate as /transcribe and /shadowing/attempt — refuse before the
    # body is parsed so revoked consent never lets the audio be read.
    if not await consent.may_transcribe(current_user.id):
        raise AuthorizationError("Transcription consent has been revoked")
    settings = get_settings()
    # Bounded, in-memory upload (#230): same gap as shadowing/attempt — a plain
    # `UploadFile` parameter has no size cap and spools past 1 MB to disk.
    data, fields = await parse_bounded_multipart(
        request,
        max_bytes=settings.max_upload_bytes,
        spool_max_size=settings.max_request_body_bytes,
    )
    target = fields.get("target")
    other = fields.get("other")
    if not target or not other:
        raise ValidationError("Missing 'target' or 'other' field")
    # #328: parse_bounded_multipart bounds the AUDIO part but not text fields — an
    # unbounded target/other would block the event loop in the sync word-normalize
    # step below and be injected into the coaching LLM prompt.
    for field_name, value in (("target", target), ("other", other)):
        if len(value) > MAX_WORD_CHARS:
            raise ValidationError(f"'{field_name}' must be at most {MAX_WORD_CHARS} characters")
    # #426: every DB read is done (auth + consent). Release before STT + coach
    # — same idle-hold #415 closed on /shadowing/attempt. native_language is
    # already loaded.
    await release_request_connection(db)
    result = await service.score_attempt(
        target=target,
        other=other,
        audio=data,
        native_language=current_user.native_language,
    )
    return PairAttemptOut(
        transcript=result.transcript,
        said_target=result.said_target,
        said_other=result.said_other,
        coaching=result.coaching,
    )
