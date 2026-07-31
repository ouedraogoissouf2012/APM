"""Per-utterance grammar correction shown DURING the conversation.

A separate, bounded LLM call (run in parallel with the reply) so the learner
sees a gentle gold correction chip — the mistake, the fix, a short grammar rule
and alternative phrasings — without interrupting the spoken flow. Any failure or
non-JSON output (e.g. the fake engine) yields *no* correction, so a correction
problem can never break a conversation turn.
"""

import json
from dataclasses import dataclass, field
from typing import Any

from app.features.conversation.messages import ROLE_USER, Message
from app.features.conversation.providers.interfaces import TextCompletionProvider
from app.features.profile.correction_style import style_for_intensity

_MAX_ALTERNATIVES = 2
_MAX_FIELD_CHARS = 400


@dataclass(frozen=True)
class TurnCorrection:
    original: str
    correction: str
    rule: str
    alternatives: list[str] = field(default_factory=list)


def _build_prompt(cefr_level: str, native_language: str, intensity: str) -> str:
    directive = style_for_intensity(intensity).prompt_directive
    return (
        "You are an English tutor. The learner just SAID one utterance during a "
        f"spoken conversation. Decide whether it contains a clear English mistake "
        f"worth correcting for a CEFR {cefr_level.upper()} learner. Ignore minor "
        "speech-recognition artifacts and acceptable informal speech. "
        f"{directive} "
        "Reply with ONLY a JSON object, no prose. If there is NO worthwhile "
        'mistake: {"has_error": false}. Otherwise: '
        '{"has_error": true, "original": "<exact fault, verbatim from the utterance>", '
        '"correction": "<the corrected form>", '
        f'"rule": "<one short grammar rule, written in the language code \'{native_language}\'>", '
        '"alternatives": ["<up to two other natural ways to say it>"]}. '
        "Keep it to the single most useful correction."
    )


class TurnCorrector:
    """Extracts at most one correction for a single learner utterance."""

    def __init__(self, llm: TextCompletionProvider, min_words: int = 1) -> None:
        self._llm = llm
        # Skip the 2nd LLM call on utterances shorter than this (#123 cost control):
        # very short turns ("yes", "ok thanks") rarely carry a worthwhile mistake.
        self._min_words = min_words

    async def correct(
        self, text: str, cefr_level: str, native_language: str, intensity: str = "gentle"
    ) -> TurnCorrection | None:
        # Cheap gate BEFORE the LLM call: too-short utterances aren't worth a
        # second round-trip. Halves the per-turn LLM cost on chatty short replies.
        if len(text.split()) < self._min_words:
            return None
        prompt = _build_prompt(cefr_level, native_language, intensity)
        try:
            raw = await self._llm.complete(prompt, [Message(role=ROLE_USER, content=text)])
        except Exception:
            # Never break a turn because the correction call failed.
            return None
        data = _loads(raw)
        if data is None or not data.get("has_error"):
            return None
        original = _clip(str(data.get("original", "")))
        correction = _clip(str(data.get("correction", "")))
        # Only trust a correction anchored in what the learner actually said,
        # and that actually changes something.
        if not original or not correction or original not in text or original == correction:
            return None
        alternatives = [_clip(str(a)) for a in data.get("alternatives", []) if str(a).strip()][
            :_MAX_ALTERNATIVES
        ]
        return TurnCorrection(
            original=original,
            correction=correction,
            rule=_clip(str(data.get("rule", ""))),
            alternatives=alternatives,
        )


def _loads(text: str) -> dict[str, Any] | None:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _clip(value: str) -> str:
    return value.strip()[:_MAX_FIELD_CHARS]
