import pytest

from app.domain.exceptions import DebriefAnalysisError
from app.features.debrief.parsing import parse_debrief_json


def test_parses_plain_json():
    data = parse_debrief_json('{"cefr_estimate": "B1", "summary": "good", "errors": []}')
    assert data["cefr_estimate"] == "B1"
    assert data["errors"] == []


def test_parses_json_wrapped_in_markdown_fences():
    raw = '```json\n{"cefr_estimate": "A2", "summary": "ok", "errors": []}\n```'
    data = parse_debrief_json(raw)
    assert data["cefr_estimate"] == "A2"


def test_parses_json_with_surrounding_prose():
    raw = 'Here is the analysis: {"cefr_estimate": "B2", "summary": "s", "errors": []} Thanks!'
    data = parse_debrief_json(raw)
    assert data["cefr_estimate"] == "B2"


def test_raises_on_unparseable_output():
    with pytest.raises(DebriefAnalysisError):
        parse_debrief_json("sorry, I cannot help with that")
