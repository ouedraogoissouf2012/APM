from fastapi import APIRouter, Depends

from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.profile.dependencies import get_profile_service
from app.features.profile.schemas import ProfileOut, ProfileUpdate
from app.features.profile.service import ProfileService

router = APIRouter(prefix="/me/profile", tags=["profile"])


@router.get("", response_model=ProfileOut)
async def get_profile(
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> ProfileOut:
    profile = await service.get_or_create(current_user.id)
    return ProfileOut.model_validate(profile)


@router.put("", response_model=ProfileOut)
async def update_profile(
    payload: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> ProfileOut:
    profile = await service.update(current_user.id, payload.model_dump(exclude_unset=True))
    return ProfileOut.model_validate(profile)
