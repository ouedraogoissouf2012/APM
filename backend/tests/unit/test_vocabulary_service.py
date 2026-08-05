"""Unit tests for the vocabulary notebook service."""

import pytest

from app.domain.exceptions import NotFoundError
from app.features.debrief.domain import VocabularyWord
from app.features.vocabulary.models import STATUS_KNOWN, STATUS_REVIEW, VocabularyEntry
from app.features.vocabulary.service import VocabularyService


class _InMemoryVocabRepository:
    def __init__(self) -> None:
        self._rows: dict[tuple[int, str], VocabularyEntry] = {}
        self._seq = 0

    async def upsert(self, user_id, session_id, word, phonetic, translation, example):
        key = (user_id, word)
        existing = self._rows.get(key)
        if existing is None:
            self._seq += 1
            self._rows[key] = VocabularyEntry(
                id=self._seq,
                user_id=user_id,
                session_id=session_id,
                word=word,
                phonetic=phonetic,
                translation=translation,
                example=example,
                status=STATUS_REVIEW,
            )
        else:
            existing.phonetic = phonetic
            existing.translation = translation
            existing.example = example
            existing.session_id = session_id
            existing.status = STATUS_REVIEW

    async def list_for_user(self, user_id):
        return [e for e in self._rows.values() if e.user_id == user_id]

    async def get_owned(self, entry_id, user_id):
        return next(
            (e for e in self._rows.values() if e.id == entry_id and e.user_id == user_id),
            None,
        )

    async def set_status(self, entry, status):
        entry.status = status
        return entry


def _service() -> tuple[VocabularyService, _InMemoryVocabRepository]:
    repo = _InMemoryVocabRepository()
    return VocabularyService(repo), repo


@pytest.mark.asyncio
async def test_capture_persists_salient_words():
    service, repo = _service()
    words = [
        VocabularyWord(
            word="deployment",
            phonetic="dɪˈplɔɪmənt",
            translation="déploiement",
            example="I handle deployments at work.",
        ),
        VocabularyWord(word="handle", translation="gérer", example="I handle deployments."),
    ]
    await service.capture(user_id=1, session_id=23, words=words)

    entries = await service.list_notebook(user_id=1)
    assert {e.word for e in entries} == {"deployment", "handle"}
    dep = next(e for e in entries if e.word == "deployment")
    assert dep.example == "I handle deployments at work."
    assert dep.session_id == 23
    assert dep.status == STATUS_REVIEW


@pytest.mark.asyncio
async def test_capture_skips_blank_words():
    service, repo = _service()
    await service.capture(1, 1, [VocabularyWord(word="   "), VocabularyWord(word="ok")])
    entries = await service.list_notebook(1)
    assert [e.word for e in entries] == ["ok"]


@pytest.mark.asyncio
async def test_reseeing_a_word_updates_not_duplicates():
    service, repo = _service()
    await service.capture(1, 1, [VocabularyWord(word="handle", example="old sentence")])
    await service.capture(1, 2, [VocabularyWord(word="handle", example="new sentence")])

    entries = await service.list_notebook(1)
    assert len(entries) == 1  # same card, refreshed
    assert entries[0].example == "new sentence"
    assert entries[0].session_id == 2


@pytest.mark.asyncio
async def test_mark_known_and_review():
    service, repo = _service()
    await service.capture(1, 1, [VocabularyWord(word="handle")])
    entry_id = (await service.list_notebook(1))[0].id

    marked = await service.mark(entry_id, user_id=1, status=STATUS_KNOWN)
    assert marked.status == STATUS_KNOWN
    back = await service.mark(entry_id, user_id=1, status=STATUS_REVIEW)
    assert back.status == STATUS_REVIEW


@pytest.mark.asyncio
async def test_mark_rejects_unknown_status():
    service, repo = _service()
    await service.capture(1, 1, [VocabularyWord(word="handle")])
    entry_id = (await service.list_notebook(1))[0].id
    with pytest.raises(ValueError):
        await service.mark(entry_id, user_id=1, status="mastered")


@pytest.mark.asyncio
async def test_mark_other_users_entry_is_not_found():
    service, repo = _service()
    await service.capture(1, 1, [VocabularyWord(word="handle")])
    entry_id = (await service.list_notebook(1))[0].id
    with pytest.raises(NotFoundError):
        await service.mark(entry_id, user_id=999, status=STATUS_KNOWN)
