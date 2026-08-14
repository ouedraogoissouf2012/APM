"""Unit tests for the export's JSON-streaming assembly (#365), isolated from
the database via a fake VoiceDataStreamSource — the whole point of depending
on that Protocol instead of the concrete repository class."""

import json
from collections.abc import AsyncIterator

import pytest

from app.features.voice_data.router import _stream_export_json


class _FakeStreamSource:
    def __init__(self, *, utterances=None, vocabulary=None, debriefs=None, review_items=None):
        self._utterances = utterances or []
        self._vocabulary = vocabulary or []
        self._debriefs = debriefs or []
        self._review_items = review_items or []

    async def stream_utterances(self, user_id: int) -> AsyncIterator[dict]:
        for item in self._utterances:
            yield item

    async def stream_vocabulary(self, user_id: int) -> AsyncIterator[dict]:
        for item in self._vocabulary:
            yield item

    async def stream_debriefs(self, user_id: int) -> AsyncIterator[dict]:
        for item in self._debriefs:
            yield item

    async def stream_review_items(self, user_id: int) -> AsyncIterator[dict]:
        for item in self._review_items:
            yield item


async def _drain(source, user_id=1) -> dict:
    body = b"".join([chunk async for chunk in _stream_export_json(source, user_id)])
    return json.loads(body)


@pytest.mark.asyncio
async def test_produces_valid_json_matching_the_schema():
    source = _FakeStreamSource(
        utterances=[{"session_id": 1, "started_at": "t", "text": "I like sports"}],
        vocabulary=[{"word": "deployment", "translation": "déploiement", "example": "..."}],
        debriefs=[
            {
                "session_id": 1,
                "started_at": "t",
                "cefr_estimate": "B1",
                "summary": "ok",
                "errors": [],
            }
        ],
        review_items=[
            {
                "error_type": "tense",
                "latest_correction": "I went",
                "stage": 1,
                "status": "due",
                "next_review_at": None,
            }
        ],
    )

    parsed = await _drain(source)

    assert parsed["raw_audio_retained"] is False
    assert parsed["utterances"] == [{"session_id": 1, "started_at": "t", "text": "I like sports"}]
    assert parsed["vocabulary"][0]["word"] == "deployment"
    assert parsed["debriefs"][0]["cefr_estimate"] == "B1"
    assert parsed["review_items"][0]["error_type"] == "tense"


@pytest.mark.asyncio
async def test_every_category_empty_still_produces_valid_json():
    parsed = await _drain(_FakeStreamSource())

    assert parsed == {
        "raw_audio_retained": False,
        "utterances": [],
        "vocabulary": [],
        "debriefs": [],
        "review_items": [],
    }


@pytest.mark.asyncio
async def test_multiple_items_in_a_category_are_comma_separated_correctly():
    # The classic hand-rolled-JSON bug: a missing/extra comma between items.
    # 3 items forces the "not first" branch to run more than once.
    source = _FakeStreamSource(
        vocabulary=[
            {"word": "a", "translation": "1", "example": ""},
            {"word": "b", "translation": "2", "example": ""},
            {"word": "c", "translation": "3", "example": ""},
        ]
    )

    parsed = await _drain(source)

    assert [v["word"] for v in parsed["vocabulary"]] == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_escapes_unicode_quotes_and_newlines_in_values():
    source = _FakeStreamSource(
        vocabulary=[
            {
                "word": "café",
                "translation": 'She said "hello"\nand left',
                "example": "100% \\ backslash",
            }
        ]
    )

    parsed = await _drain(source)

    assert parsed["vocabulary"][0]["word"] == "café"
    assert parsed["vocabulary"][0]["translation"] == 'She said "hello"\nand left'
    assert parsed["vocabulary"][0]["example"] == "100% \\ backslash"


@pytest.mark.asyncio
async def test_first_category_empty_and_later_categories_populated():
    # Guards the "first" flag being per-category, not shared/stuck across them.
    source = _FakeStreamSource(
        utterances=[],
        vocabulary=[{"word": "x", "translation": "y", "example": ""}],
    )

    parsed = await _drain(source)

    assert parsed["utterances"] == []
    assert parsed["vocabulary"] == [{"word": "x", "translation": "y", "example": ""}]
