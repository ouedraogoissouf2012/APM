from fastapi import APIRouter, Depends, Request, status

from app.core.rate_limit import RateLimiter
from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.missions.dependencies import (
    get_mission_rate_limiter,
    get_mission_service,
)
from app.features.missions.schemas import MissionIn, MissionOut
from app.features.missions.service import MissionService

router = APIRouter(prefix="/missions", tags=["missions"])


@router.post("", response_model=MissionOut, status_code=status.HTTP_201_CREATED)
async def create_mission(
    payload: MissionIn,
    request: Request,
    current_user: User = Depends(get_current_user),
    limiter: RateLimiter = Depends(get_mission_rate_limiter),
    service: MissionService = Depends(get_mission_service),
) -> MissionOut:
    client_host = request.client.host if request.client else "anonymous"
    await limiter.check(f"mission:{client_host}:user:{current_user.id}")
    mission = await service.create(current_user, payload.source_type, payload.content)
    return MissionOut.model_validate(mission)


@router.get("/{mission_id}", response_model=MissionOut)
async def get_mission(
    mission_id: int,
    current_user: User = Depends(get_current_user),
    service: MissionService = Depends(get_mission_service),
) -> MissionOut:
    mission = await service.get(mission_id, current_user)
    return MissionOut.model_validate(mission)
