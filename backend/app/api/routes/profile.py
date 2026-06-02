from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.learner_profile import LearnerProfile
from app.models.user import User
from app.schemas.profile import ProfileOut, ProfileUpdate

router = APIRouter(prefix="/me/profile", tags=["profile"])


async def _get_or_create(db: AsyncSession, user_id: int) -> LearnerProfile:
    profile = await db.get(LearnerProfile, user_id)
    if profile is None:
        profile = LearnerProfile(user_id=user_id)
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    return profile


@router.get("", response_model=ProfileOut)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    profile = await _get_or_create(db, current_user.id)
    return ProfileOut.model_validate(profile)


@router.put("", response_model=ProfileOut)
async def update_profile(
    payload: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    profile = await _get_or_create(db, current_user.id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(profile, key, value)
    await db.commit()
    await db.refresh(profile)
    return ProfileOut.model_validate(profile)
