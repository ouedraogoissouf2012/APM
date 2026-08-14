"""Coach a shadowing attempt: one short, targeted tip on the missed words.

Like the turn corrector, a coaching failure must never break the attempt flow —
it returns empty coaching rather than raising. When nothing was missed there is
nothing to coach, so no LLM call is made at all.
"""

import logging

from app.core.llm.interfaces import TextCompletionProvider
from app.core.llm.messages import ROLE_USER, Message
from app.core.llm_json import clip, parse_json_object
from app.core.prompt_safety import render_untrusted_block

_MAX_COACHING_CHARS = 400
_logger = logging.getLogger(__name__)


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
            # Never break the attempt because coaching failed (#236: but log it —
            # the learner silently loses the coaching tip with no server trace).
            _logger.warning("Shadowing coaching LLM call failed", exc_info=True)
            return ""

        data = parse_json_object(raw)
        if data is None:
            return ""
        return clip(str(data.get("coaching", "")), _MAX_COACHING_CHARS)
