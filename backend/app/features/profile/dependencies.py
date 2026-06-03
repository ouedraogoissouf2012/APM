from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.features.profile.repository import ProfileRepository, SqlAlchemyProfileRepository
from app.features.profile.service import ProfileService


def get_profile_repository(db: AsyncSession = Depends(get_db)) -> ProfileRepository:
    return SqlAlchemyProfileRepository(db)


def get_profile_service(
    profiles: ProfileRepository = Depends(get_profile_repository),
) -> ProfileService:
    return ProfileService(profiles)
