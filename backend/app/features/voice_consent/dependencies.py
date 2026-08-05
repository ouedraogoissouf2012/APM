from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.features.voice_consent.repository import SqlAlchemyVoiceConsentRepository
from app.features.voice_consent.service import VoiceConsentService


def get_voice_consent_service(db: AsyncSession = Depends(get_db)) -> VoiceConsentService:
    return VoiceConsentService(SqlAlchemyVoiceConsentRepository(db))
