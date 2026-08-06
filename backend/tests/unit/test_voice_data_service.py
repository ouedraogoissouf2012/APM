"""Unit tests for the voice-data export/erase service (#128, #186)."""

import pytest

from app.features.voice_data.service import VoiceDataService


class _StubSource:
    def __init__(self, utterances=None, vocabulary=None, debriefs=None, reviews=None, counts=None):
        self._utterances = utterances or []
        self._vocabulary = vocabulary or []
        self._debriefs = debriefs or []
        self._reviews = reviews or []
        self._counts = counts or {}
        self.purged_user: int | None = None

    async def utterances(self, user_id):
        return self._utterances

    async def vocabulary(self, user_id):
        return self._vocabulary

    async def debriefs(self, user_id):
        return self._debriefs

    async def review_items(self, user_id):
        return self._reviews

    async def purge(self, user_id):
        self.purged_user = user_id
        return self._counts


@pytest.mark.asyncio
async def test_export_bundles_every_voice_derived_category():
    source = _StubSource(
        utterances=[{"session_id": 1, "started_at": "t", "text": "I like sports"}],
        vocabulary=[{"word": "deployment", "translation": "déploiement", "example": "..."}],
        debriefs=[{"session_id": 1, "started_at": "t", "cefr_estimate": "B1", "summary": "ok"}],
        reviews=[{"error_type": "tense", "latest_correction": "I went", "status": "due"}],
    )
    export = await VoiceDataService(source).export(user_id=1)

    assert export.raw_audio_retained is False  # honest: never stored
    assert export.utterances[0]["text"] == "I like sports"
    assert export.vocabulary[0]["word"] == "deployment"
    # The service now honours its docstring: debriefs + review items are exported.
    assert export.debriefs[0]["cefr_estimate"] == "B1"
    assert export.review_items[0]["error_type"] == "tense"


@pytest.mark.asyncio
async def test_export_is_empty_for_a_fresh_user():
    export = await VoiceDataService(_StubSource()).export(user_id=1)
    assert export.utterances == []
    assert export.vocabulary == []
    assert export.debriefs == []
    assert export.review_items == []


@pytest.mark.asyncio
async def test_erase_delegates_to_the_source_and_returns_counts():
    source = _StubSource(counts={"transcripts": 2, "vocabulary": 5})
    counts = await VoiceDataService(source).erase(user_id=42)

    assert source.purged_user == 42
    assert counts == {"transcripts": 2, "vocabulary": 5}
