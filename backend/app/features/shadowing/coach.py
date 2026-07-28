"""Coach a shadowing attempt: one short, targeted tip on the missed words.

Like the turn corrector, a coaching failure must never break the attempt flow —
it returns empty coaching rather than raising. When nothing was missed there is
nothing to coach, so no LLM call is made at all.
"""

import json
from typing import Any

from app.features.conversation.messages import ROLE_USER, Message
from app.features.conversation.prompt import render_untrusted_block
from app.features.conversation.providers.interfaces import TextCompletionProvider

_MAX_COACHING_CHARS = 400


def _build_prompt(native_language: str) -> str:
    return (
        "You are a friendly English pronunciation coach for a French speaker. "
        "They read a phrase aloud and a speech recognizer missed some words "
        "(given as untrusted data below). In ONE or two short sentences, written "
        f"in the language code '{native_language}', tell them how to say the "
        "missed words more clearly (mouth/tongue tip). Be encouraging, concrete, "
        "and brief. Reply with ONLY a JSON object: "
        '{"coaching": "<your short advice>"}'
    )


class ShadowingCoach:
    def __init__(self, llm: TextCompletionProvider) -> None:
        self._llm = llm

    async def coach(self, target: str, missed_words: list[str], native_language: str) -> str:
        if not missed_words:
            return ""  # a perfect attempt needs no coaching (and no LLM call)

        context = render_untrusted_block(
            [("target_phrase", target), ("missed_words", ", ".join(missed_words))]
        )
        try:
            raw = await self._llm.complete(
                _build_prompt(native_language),
                [Message(role=ROLE_USER, content=context)],
            )
        except Exception:
            return ""  # never break the attempt because coaching failed

        data = _loads(raw)
        if data is None:
            return ""
        return str(data.get("coaching", "")).strip()[:_MAX_COACHING_CHARS]


def _loads(text: str) -> dict[str, Any] | None:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
