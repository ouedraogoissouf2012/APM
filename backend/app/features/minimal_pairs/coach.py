"""Coach a minimal-pair confusion: one short tip when the learner said the wrong
word of the pair (or missed the target). Like the shadowing coach, a failure
returns empty coaching rather than raising, and no LLM call is made when the
attempt was correct.
"""

import json
from typing import Any

from app.features.conversation.messages import ROLE_USER, Message
from app.features.conversation.prompt import render_untrusted_block
from app.features.conversation.providers.interfaces import TextCompletionProvider

_MAX_COACHING_CHARS = 400


def _build_prompt(native_language: str) -> str:
    return (
        "You are a friendly English pronunciation coach for a French speaker "
        "practising a minimal pair (two words differing by one sound). They were "
        "asked to say the TARGET word but the recognizer heard something else "
        "(untrusted data below). In ONE or two short sentences, written in the "
        f"language code '{native_language}', tell them how to make the target "
        "sound distinct (mouth/tongue tip). Be encouraging and concrete. Reply "
        'with ONLY a JSON object: {"coaching": "<your short advice>"}'
    )


class PairCoach:
    def __init__(self, llm: TextCompletionProvider) -> None:
        self._llm = llm

    async def coach(self, target: str, other: str, said_other: bool, native_language: str) -> str:
        context = render_untrusted_block(
            [
                ("target_word", target),
                ("other_word_of_pair", other),
                ("said_the_other_word", "yes" if said_other else "no"),
            ]
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
