from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.persistence import first_touch_by_user_id
from app.features.voice_consent.models import VoiceConsent


class VoiceConsentRepository(Protocol):
    async def get_by_user_id(self, user_id: int) -> VoiceConsent | None: ...

    async def get_or_create(self, user_id: int) -> VoiceConsent: ...

    async def save(self, consent: VoiceConsent) -> VoiceConsent: ...


class SqlAlchemyVoiceConsentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_id(self, user_id: int) -> VoiceConsent | None:
        return await self._session.scalar(
            select(VoiceConsent).where(VoiceConsent.user_id == user_id)
        )

    async def get_or_create(self, user_id: int) -> VoiceConsent:
        # Atomic first-touch (#371, core.persistence): a plain get-then-create
        # races two concurrent first requests into a double INSERT that trips
        # the unique(user_id) constraint — one 500. The protective defaults
        # come from the columns' server_defaults (see the model).
        return await first_touch_by_user_id(self._session, VoiceConsent, user_id)

    async def save(self, consent: VoiceConsent) -> VoiceConsent:
        await self._session.commit()
        await self._session.refresh(consent)
        return consent
