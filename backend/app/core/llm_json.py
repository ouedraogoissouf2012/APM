"""Shared LLM free-form-output helpers (#366).

`parse_json_object` was byte-for-byte duplicated in 5 feature modules
(conversation/correction.py, minimal_pairs/coach.py, shadowing/coach.py,
shadowing/generator.py, missions/compiler.py) — a hardening of the parsing
(e.g. #238's wrongly-typed-payload guard) had to be replicated in every copy,
and a missed one would silently diverge from the others. `clip` was duplicated
3 times among them. Centralised here so there is exactly one place to harden.
"""

import json
from typing import Any


def parse_json_object(text: str) -> dict[str, Any] | None:
    """Extract the JSON object between the first '{' and the last '}' in
    `text` (handles code fences/prose wrapping the actual JSON) and parse it.
    Returns None — never raises — on missing braces, invalid JSON, or a
    non-dict top-level value, so callers degrade to "no result" instead of
    crashing on free-form LLM output."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def clip(value: str, max_chars: int) -> str:
    """Strip whitespace and bound `value` to `max_chars` — the shared idiom
    for keeping an LLM-generated/untrusted string from growing unbounded
    before it's stored or sent to a client."""
    return value.strip()[:max_chars]
