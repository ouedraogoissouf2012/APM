from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.features.voice_data.repository import SqlAlchemyVoiceDataSource
from app.features.voice_data.service import VoiceDataService


def get_voice_data_service(db: AsyncSession = Depends(get_db)) -> VoiceDataService:
    return VoiceDataService(SqlAlchemyVoiceDataSource(db))
