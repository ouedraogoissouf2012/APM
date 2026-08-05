from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.voice_consent.models import VoiceConsent


class VoiceConsentRepository(Protocol):
    async def get_by_user_id(self, user_id: int) -> VoiceConsent | None: ...

    async def create(self, consent: VoiceConsent) -> VoiceConsent: ...

    async def save(self, consent: VoiceConsent) -> VoiceConsent: ...


class SqlAlchemyVoiceConsentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_id(self, user_id: int) -> VoiceConsent | None:
        return await self._session.scalar(
            select(VoiceConsent).where(VoiceConsent.user_id == user_id)
        )

    async def create(self, consent: VoiceConsent) -> VoiceConsent:
        self._session.add(consent)
        await self._session.commit()
        await self._session.refresh(consent)
        return consent

    async def save(self, consent: VoiceConsent) -> VoiceConsent:
        await self._session.commit()
        await self._session.refresh(consent)
        return consent
