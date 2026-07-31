from fastapi import APIRouter, Depends, Request, status

from app.api.client_ip import client_ip
from app.config import get_settings
from app.core.rate_limit import RateLimiter
from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.debrief.dependencies import get_debrief_rate_limiter, get_debrief_service
from app.features.debrief.schemas import DebriefOut
from app.features.debrief.service import DebriefService

router = APIRouter(prefix="/sessions/{session_id}/debrief", tags=["debrief"])


@router.post("", response_model=DebriefOut, status_code=status.HTTP_201_CREATED)
async def generate_debrief(
    session_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    limiter: RateLimiter = Depends(get_debrief_rate_limiter),
    service: DebriefService = Depends(get_debrief_service),
) -> DebriefOut:
    client_host = client_ip(request, get_settings().trust_proxy_headers)
    await limiter.check(f"debrief:{client_host}:user:{current_user.id}")
    debrief = await service.generate(session_id, current_user)
    return DebriefOut.model_validate(debrief)


@router.get("", response_model=DebriefOut)
async def get_debrief(
    session_id: int,
    current_user: User = Depends(get_current_user),
    service: DebriefService = Depends(get_debrief_service),
) -> DebriefOut:
    debrief = await service.get(session_id, current_user)
    return DebriefOut.model_validate(debrief)
