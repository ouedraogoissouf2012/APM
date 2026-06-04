import json
from typing import Any

from app.domain.exceptions import DebriefAnalysisError


def _extract_json_object(text: str) -> str:
    """Return the substring from the first '{' to the last '}' (handles code fences/prose)."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise DebriefAnalysisError("No JSON object found in LLM output")
    return text[start : end + 1]


def parse_debrief_json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(_extract_json_object(text))
    except json.JSONDecodeError as exc:
        raise DebriefAnalysisError(f"Invalid JSON from debrief LLM: {exc}") from exc
    if not isinstance(data, dict):
        raise DebriefAnalysisError("Debrief LLM output is not a JSON object")
    return data
