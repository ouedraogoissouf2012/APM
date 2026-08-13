from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request

from app.core.rate_limit import RateLimiter, user_rate_limit_key
from app.features.analytics.dependencies import get_analytics_service
from app.features.analytics.service import AnalyticsService
from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.missions.dependencies import (
    get_mission_rate_limiter,
    get_mission_service,
)
from app.features.missions.schemas import MissionOut
from app.features.missions.service import MissionService
from app.features.transfer.service import TransferService

router = APIRouter(prefix="/me/transfer", tags=["transfer"])


@router.post("/{skill}", response_model=MissionOut)
async def create_transfer_challenge(
    # Bounded at the edge: the skill is a free path segment that flows into an LLM
    # compilation prompt AND into a stored analytics property, so cap its length
    # (422 past 64 chars) and reject a blank/whitespace-only value before use.
    skill: Annotated[str, Path(min_length=1, max_length=64)],
    request: Request,
    current_user: User = Depends(get_current_user),
    limiter: RateLimiter = Depends(get_mission_rate_limiter),
    missions: MissionService = Depends(get_mission_service),
    analytics: AnalyticsService = Depends(get_analytics_service),
) -> MissionOut:
    """Compile a surprise-transfer challenge for a skill: a novel equivalent
    role-play in an unfamiliar context. Returns a mission the learner launches
    like any other (mode='mission'); the debrief then evaluates the attempt.
    Reuses the mission rate-limit (it is an LLM compilation)."""
    skill = skill.strip()
    if not skill:
        raise HTTPException(status_code=422, detail="skill must not be blank")
    await limiter.check(user_rate_limit_key("transfer", current_user.id))
    mission = await TransferService(missions).challenge(current_user, skill)
    # Product analytics (#129): a transfer challenge was started. Best-effort.
    await analytics.transfer_started(current_user.id, skill)
    return MissionOut.model_validate(mission)
