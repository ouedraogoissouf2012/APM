from fastapi import APIRouter, Depends, Form, Request, UploadFile

from app.api.client_ip import client_ip
from app.config import get_settings
from app.core.rate_limit import RateLimiter
from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.minimal_pairs.dependencies import (
    get_minimal_pairs_rate_limiter,
    get_minimal_pairs_service,
)
from app.features.minimal_pairs.schemas import PairAttemptOut
from app.features.minimal_pairs.service import MinimalPairsService

router = APIRouter(prefix="/minimal-pairs", tags=["minimal-pairs"])


@router.post("/attempt", response_model=PairAttemptOut)
async def score_attempt(
    request: Request,
    audio: UploadFile,
    target: str = Form(...),
    other: str = Form(...),
    current_user: User = Depends(get_current_user),
    limiter: RateLimiter = Depends(get_minimal_pairs_rate_limiter),
    service: MinimalPairsService = Depends(get_minimal_pairs_service),
) -> PairAttemptOut:
    """Score a spoken minimal-pair attempt: did the learner say the target word,
    or the other (confused) word of the pair? The audio is used then discarded."""
    client_host = client_ip(request, get_settings().trust_proxy_headers)
    await limiter.check(f"minimal-pairs:{client_host}:user:{current_user.id}")
    data = await audio.read()
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
