from typing import Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

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
        # Atomic first-touch: INSERT ... ON CONFLICT DO NOTHING, then read back.
        # A plain get-then-create races two concurrent first requests into a double
        # INSERT that trips the unique(user_id) constraint — one 500s. Here the
        # loser's insert is a no-op and both read the same row. The protective
        # defaults come from the columns' server_defaults (see the model).
        await self._session.execute(
            pg_insert(VoiceConsent)
            .values(user_id=user_id)
            .on_conflict_do_nothing(index_elements=["user_id"])
        )
        await self._session.commit()
        consent = await self.get_by_user_id(user_id)
        assert consent is not None  # just inserted, or already present
        return consent

    async def save(self, consent: VoiceConsent) -> VoiceConsent:
        await self._session.commit()
        await self._session.refresh(consent)
        return consent
