"""Vocabulary notebook business logic.

The debrief analyzer surfaces 1-3 salient words per session (each with the
learner's own sentence). This service persists them into a per-user notebook and
lets the learner mark a card "known" or "review". The spaced-repetition schedule
(#117) builds on the stored status; here we only capture and toggle it.
"""

from app.core.pagination import resolve_limit
from app.domain.exceptions import NotFoundError
from app.features.debrief.domain import VocabularyWord
from app.features.vocabulary.models import (
    STATUS_KNOWN,
    STATUS_REVIEW,
    VocabularyEntry,
)
from app.features.vocabulary.repository import VocabularyRepository

_VALID_STATUS = {STATUS_REVIEW, STATUS_KNOWN}


class VocabularyService:
    def __init__(self, repo: VocabularyRepository) -> None:
        self._repo = repo

    async def capture(
        self, user_id: int, session_id: int | None, words: list[VocabularyWord]
    ) -> None:
        """Persist the debrief's salient words. Best-effort per word: a blank word
        is skipped; capturing is never allowed to break the debrief that produced it."""
        for w in words:
            word = w.word.strip()
            if not word:
                continue
            await self._repo.upsert(
                user_id=user_id,
                session_id=session_id,
                word=word,
                phonetic=w.phonetic.strip(),
                translation=w.translation.strip(),
                example=w.example.strip(),
            )

    async def list_notebook(
        self, user_id: int, *, limit: int | None = None, before_id: int | None = None
    ) -> list[VocabularyEntry]:
        """One page of the notebook, newest first. ``before_id`` is a keyset
        cursor (the last id seen). The limit is clamped so a caller can never
        request an unbounded page."""
        return await self._repo.list_for_user(
            user_id, limit=resolve_limit(limit), before_id=before_id
        )

    async def mark(self, entry_id: int, user_id: int, status: str) -> VocabularyEntry:
        if status not in _VALID_STATUS:
            raise ValueError(f"Unknown vocabulary status: {status!r}")
        entry = await self._repo.get_owned(entry_id, user_id)
        if entry is None:
            raise NotFoundError("Vocabulary entry not found")
        return await self._repo.set_status(entry, status)
