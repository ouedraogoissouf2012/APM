from typing import Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.vocabulary.models import STATUS_REVIEW, VocabularyEntry


class VocabularyRepository(Protocol):
    async def upsert(
        self,
        user_id: int,
        session_id: int | None,
        word: str,
        phonetic: str,
        translation: str,
        example: str,
    ) -> None:
        """Insert a card, or refresh its context if the (user, word) already exists."""
        ...

    async def list_for_user(
        self, user_id: int, *, limit: int, before_id: int | None = None
    ) -> list[VocabularyEntry]:
        """One page of the user's notebook, newest first. ``before_id`` is a
        keyset cursor: pass the last id already seen to get the next page."""
        ...

    async def get_owned(self, entry_id: int, user_id: int) -> VocabularyEntry | None: ...

    async def set_status(self, entry: VocabularyEntry, status: str) -> VocabularyEntry: ...


class SqlAlchemyVocabularyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        user_id: int,
        session_id: int | None,
        word: str,
        phonetic: str,
        translation: str,
        example: str,
    ) -> None:
        # ON CONFLICT (user_id, word): re-seeing a word refreshes its context and
        # resets it to "review" (it's freshly relevant again) without duplicating
        # the card. Atomic — no read-modify-write race between concurrent debriefs.
        stmt = pg_insert(VocabularyEntry).values(
            user_id=user_id,
            session_id=session_id,
            word=word,
            phonetic=phonetic,
            translation=translation,
            example=example,
            status=STATUS_REVIEW,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_vocabulary_user_word",
            set_={
                "phonetic": stmt.excluded.phonetic,
                "translation": stmt.excluded.translation,
                "example": stmt.excluded.example,
                "session_id": stmt.excluded.session_id,
                "status": STATUS_REVIEW,
            },
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def list_for_user(
        self, user_id: int, *, limit: int, before_id: int | None = None
    ) -> list[VocabularyEntry]:
        stmt = select(VocabularyEntry).where(VocabularyEntry.user_id == user_id)
        if before_id is not None:
            stmt = stmt.where(VocabularyEntry.id < before_id)
        # id DESC == newest first: ids are monotonic with created_at
        # (autoincrement), so this preserves the previous created_at DESC order
        # while giving a single-column keyset cursor that scales past OFFSET.
        stmt = stmt.order_by(VocabularyEntry.id.desc()).limit(limit)
        result = await self._session.scalars(stmt)
        return list(result)

    async def get_owned(self, entry_id: int, user_id: int) -> VocabularyEntry | None:
        return await self._session.scalar(
            select(VocabularyEntry).where(
                VocabularyEntry.id == entry_id,
                VocabularyEntry.user_id == user_id,
            )
        )

    async def set_status(self, entry: VocabularyEntry, status: str) -> VocabularyEntry:
        entry.status = status
        await self._session.commit()
        await self._session.refresh(entry)
        return entry
