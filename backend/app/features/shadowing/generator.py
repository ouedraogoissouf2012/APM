"""Generate a shadowing target phrase via one LLM call.

Mirrors MissionCompiler's shape (bounded LLM call, robust JSON parse). Unlike the
mission compiler, a generation failure is NOT a hard error: shadowing must always
have a phrase to practise, so we fall back to a safe canned phrase per CEFR level
rather than 502-ing.
"""

import logging

from app.core.llm_json import clip, parse_json_object
from app.features.conversation.providers.interfaces import TextCompletionProvider
from app.features.shadowing.domain import PhoneticFocus, ShadowingPhrase

_MAX_TEXT_CHARS = 200
_MAX_TIP_CHARS = 200
_logger = logging.getLogger(__name__)
_VALID_FOCUS: frozenset[str] = frozenset(PhoneticFocus.__args__)  # type: ignore[attr-defined]

# Safe fallbacks so the fake engine (or any parse failure) still gives a usable,
# French-speaker-relevant phrase to practise.
_FALLBACK_BY_LEVEL: dict[str, ShadowingPhrase] = {
    "A1": ShadowingPhrase(
        "This is my house.", "th", "Put your tongue between your teeth for 'th'."
    ),
    "A2": ShadowingPhrase("The ship is sinking.", "ship_sheep", "Keep the vowel short in 'ship'."),
    "B1": ShadowingPhrase("He happily helped her.", "h", "Breathe out the 'h' — don't drop it."),
    "B2": ShadowingPhrase(
        "I thought they worked hard.", "ed_endings", "The '-ed' in 'worked' sounds like /t/."
    ),
}
_DEFAULT_FALLBACK = _FALLBACK_BY_LEVEL["A2"]


def _build_prompt(cefr_level: str) -> str:
    return (
        "You generate ONE short English phrase for a French speaker to practise "
        f"by shadowing (reading aloud), suited to CEFR level {cefr_level.upper()}. "
        "Target a sound French speakers of English struggle with. "
        "Reply with ONLY a JSON object, no prose: "
        '{"text": "<one natural phrase, 3-8 words>", '
        '"focus": "<one of: th, h, ship_sheep, ed_endings, word_stress, general>", '
        '"tip": "<one short articulation tip>"}'
    )


class PhraseGenerator:
    def __init__(self, llm: TextCompletionProvider) -> None:
        self._llm = llm

    async def generate(self, cefr_level: str) -> ShadowingPhrase:
        fallback = _FALLBACK_BY_LEVEL.get(cefr_level.upper(), _DEFAULT_FALLBACK)
        try:
            raw = await self._llm.complete(_build_prompt(cefr_level), [])
        except Exception:
            # A canned fallback keeps shadowing usable (#236: but log it — a silent
            # fallback to the same canned phrase every time is invisible otherwise).
            _logger.warning("Shadowing phrase generation LLM call failed", exc_info=True)
            return fallback

        data = parse_json_object(raw)
        if data is None:
            return fallback
        text = clip(str(data.get("text", "")), _MAX_TEXT_CHARS)
        if not text:
            return fallback
        focus_raw = str(data.get("focus", "general"))
        focus: PhoneticFocus = focus_raw if focus_raw in _VALID_FOCUS else "general"  # type: ignore[assignment]
        return ShadowingPhrase(
            text=text,
            focus=focus,
            tip=clip(str(data.get("tip", "")), _MAX_TIP_CHARS),
        )
