from fastapi import APIRouter, Depends, Request

from app.api.client_ip import client_ip
from app.config import get_settings
from app.core.rate_limit import RateLimiter
from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.onboarding.dependencies import (
    get_onboarding_rate_limiter,
    get_onboarding_service,
)
from app.features.onboarding.schemas import PlacementIn, PlacementOut
from app.features.onboarding.service import OnboardingService

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post("/placement", response_model=PlacementOut)
async def submit_placement(
    payload: PlacementIn,
    request: Request,
    current_user: User = Depends(get_current_user),
    limiter: RateLimiter = Depends(get_onboarding_rate_limiter),
    service: OnboardingService = Depends(get_onboarding_service),
) -> PlacementOut:
    """Estimate the learner's starting CEFR from their spoken placement answers and
    pre-fill interests/goal. Idempotent enough to retry: it re-runs the estimate
    and overwrites the level/profile from the submitted answers."""
    client_host = client_ip(request, get_settings().trust_proxy_headers)
    await limiter.check(f"placement:{client_host}:user:{current_user.id}")
    result = await service.place(current_user, payload.answers, payload.interests, payload.goal)
    return PlacementOut(
        cefr_level=result.cefr_level,
        interests=result.interests,
        goal=result.goal,
    )
