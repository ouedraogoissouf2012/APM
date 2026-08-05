"""Unit tests for the voice-data export/erase service (#128)."""

import pytest

from app.features.voice_data.service import VoiceDataService


class _StubSource:
    def __init__(self, utterances=None, vocabulary=None, counts=None):
        self._utterances = utterances or []
        self._vocabulary = vocabulary or []
        self._counts = counts or {}
        self.purged_user: int | None = None

    async def utterances(self, user_id):
        return self._utterances

    async def vocabulary(self, user_id):
        return self._vocabulary

    async def purge(self, user_id):
        self.purged_user = user_id
        return self._counts


@pytest.mark.asyncio
async def test_export_bundles_utterances_and_vocabulary():
    source = _StubSource(
        utterances=[{"session_id": 1, "started_at": "t", "text": "I like sports"}],
        vocabulary=[{"word": "deployment", "translation": "déploiement", "example": "..."}],
    )
    export = await VoiceDataService(source).export(user_id=1)

    assert export.raw_audio_retained is False  # honest: never stored
    assert export.utterances[0]["text"] == "I like sports"
    assert export.vocabulary[0]["word"] == "deployment"


@pytest.mark.asyncio
async def test_export_is_empty_for_a_fresh_user():
    export = await VoiceDataService(_StubSource()).export(user_id=1)
    assert export.utterances == []
    assert export.vocabulary == []


@pytest.mark.asyncio
async def test_erase_delegates_to_the_source_and_returns_counts():
    source = _StubSource(counts={"transcripts": 2, "vocabulary": 5})
    counts = await VoiceDataService(source).erase(user_id=42)

    assert source.purged_user == 42
    assert counts == {"transcripts": 2, "vocabulary": 5}
