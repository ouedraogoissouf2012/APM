"""Unit tests for the export's JSON-streaming assembly (#365), isolated from
the database via fake async iterators — the whole point of
_assemble_export_json being DB-agnostic (it takes already-built async
iterators, not a session/repository)."""

import json
from collections.abc import AsyncIterator

import pytest

from app.features.voice_data.router import _assemble_export_json


async def _aiter(items: list[dict]) -> AsyncIterator[dict]:
    for item in items:
        yield item


def _categories(
    *, utterances=None, vocabulary=None, debriefs=None, review_items=None
) -> tuple[tuple[str, AsyncIterator[dict]], ...]:
    return (
        ("utterances", _aiter(utterances or [])),
        ("vocabulary", _aiter(vocabulary or [])),
        ("debriefs", _aiter(debriefs or [])),
        ("review_items", _aiter(review_items or [])),
    )


async def _drain(categories: tuple[tuple[str, AsyncIterator[dict]], ...]) -> dict:
    body = b"".join([chunk async for chunk in _assemble_export_json(categories)])
    return json.loads(body)


@pytest.mark.asyncio
async def test_produces_valid_json_matching_the_schema():
    categories = _categories(
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

    parsed = await _drain(categories)

    assert parsed["raw_audio_retained"] is False
    assert parsed["utterances"] == [{"session_id": 1, "started_at": "t", "text": "I like sports"}]
    assert parsed["vocabulary"][0]["word"] == "deployment"
    assert parsed["debriefs"][0]["cefr_estimate"] == "B1"
    assert parsed["review_items"][0]["error_type"] == "tense"


@pytest.mark.asyncio
async def test_every_category_empty_still_produces_valid_json():
    parsed = await _drain(_categories())

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
    categories = _categories(
        vocabulary=[
            {"word": "a", "translation": "1", "example": ""},
            {"word": "b", "translation": "2", "example": ""},
            {"word": "c", "translation": "3", "example": ""},
        ]
    )

    parsed = await _drain(categories)

    assert [v["word"] for v in parsed["vocabulary"]] == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_escapes_unicode_quotes_and_newlines_in_values():
    categories = _categories(
        vocabulary=[
            {
                "word": "café",
                "translation": 'She said "hello"\nand left',
                "example": "100% \\ backslash",
            }
        ]
    )

    parsed = await _drain(categories)

    assert parsed["vocabulary"][0]["word"] == "café"
    assert parsed["vocabulary"][0]["translation"] == 'She said "hello"\nand left'
    assert parsed["vocabulary"][0]["example"] == "100% \\ backslash"


@pytest.mark.asyncio
async def test_first_category_empty_and_later_categories_populated():
    # Guards the "first" flag being per-category, not shared/stuck across them.
    categories = _categories(
        utterances=[],
        vocabulary=[{"word": "x", "translation": "y", "example": ""}],
    )

    parsed = await _drain(categories)

    assert parsed["utterances"] == []
    assert parsed["vocabulary"] == [{"word": "x", "translation": "y", "example": ""}]
