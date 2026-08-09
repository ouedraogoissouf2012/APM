import logging
import re
from collections.abc import AsyncIterator
from typing import Any

from app.domain.exceptions import LlmProviderError
from app.features.conversation.messages import Message

logger = logging.getLogger(__name__)

# A sentence boundary: terminal punctuation (+ optional closing quotes/brackets)
# FOLLOWED BY whitespace — the start of the next sentence. Requiring the trailing
# space (instead of treating end-of-buffer as a boundary) is what keeps a decimal
# like "3.50" whole: that period is followed by a digit, not a space. The final
# sentence has no trailing space and is flushed by the tail logic at stream end.
_SENTENCE_END = re.compile(r'[.!?]+["\')\]]*(?=\s)')

# Words that end in a period WITHOUT ending a sentence, so we don't chop "Mr.
# Smith" or "e.g. apples" into robotic half-utterances. Matched case-insensitively
# against the token before a lone period; single-letter initials ("J. R.") are
# treated the same way.
_ABBREVIATIONS = frozenset(
    {
        "mr",
        "mrs",
        "ms",
        "dr",
        "prof",
        "st",
        "sr",
        "jr",
        "vs",
        "etc",
        "e.g",
        "i.e",
        "a.m",
        "p.m",
        "u.s",
        "u.k",
    }
)
_TRAILING_WORD = re.compile(r"([A-Za-z][A-Za-z.]*)$")


def _ends_with_abbreviation(text_before_period: str) -> bool:
    """True when the letters just before a lone terminal '.' form a known
    abbreviation or a single-letter initial — i.e. not a real sentence end."""
    word_match = _TRAILING_WORD.search(text_before_period)
    if word_match is None:
        return False
    word = word_match.group(1).lower().strip(".")
    if not word:
        return False
    return len(word) == 1 or word in _ABBREVIATIONS


class OpenAiCompatibleLlmProvider:
    """LLM stage backed by any OpenAI-compatible chat API (DeepSeek, Groq, ...).

    The async client is injected so the provider is unit-testable without a key.
    The provider itself is vendor-neutral — only the injected client's base_url and
    the `model` differ between DeepSeek and Groq. Groq (Llama 3.3) has a far lower
    time-to-first-token (~0.4 s vs ~2-4 s), which is why it can back the live turn.
    """

    def __init__(
        self, client: Any, model: str, max_tokens: int, extra_body: dict[str, Any] | None = None
    ) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        # Vendor-specific request params passed through to the API. For DeepSeek we
        # send {"thinking": {"type": "disabled"}}: its flash model reasons before
        # answering BY DEFAULT (~14 s time-to-first-token), which is useless for a
        # live chat — disabling it drops the reply to ~1.5 s. Empty for Groq (which
        # doesn't accept the param).
        self._extra_body = extra_body or {}

    async def complete(self, system_prompt: str, history: list[Message]) -> str:
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        messages += [{"role": m.role, "content": m.content} for m in history]
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=self._max_tokens,
                extra_body=self._extra_body,
            )
        except Exception as exc:
            logger.warning("LLM provider failed: %s", exc.__class__.__name__)
            raise LlmProviderError("LLM provider failed") from exc
        return response.choices[0].message.content or ""

    async def stream_complete(
        self, system_prompt: str, history: list[Message]
    ) -> AsyncIterator[str]:
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        messages += [{"role": m.role, "content": m.content} for m in history]
        buffer = ""
        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=self._max_tokens,
                stream=True,
                extra_body=self._extra_body,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if not delta:
                    continue
                buffer += delta
                # Emit every complete sentence sitting in the buffer.
                search_from = 0
                while True:
                    match = _SENTENCE_END.search(buffer, search_from)
                    if match is None:
                        break
                    end = match.end()
                    # A lone period after an abbreviation/initial isn't a real
                    # boundary — keep it in the sentence and look further along.
                    core = match.group().rstrip("\"')]")
                    if core == "." and _ends_with_abbreviation(buffer[: match.start()]):
                        search_from = end
                        continue
                    sentence = buffer[:end].strip()
                    buffer = buffer[end:]
                    search_from = 0
                    if sentence:
                        yield sentence
        except Exception as exc:
            logger.warning("LLM stream failed: %s", exc.__class__.__name__)
            raise LlmProviderError("LLM provider failed") from exc
        # Flush any trailing text that did not end with punctuation.
        tail = buffer.strip()
        if tail:
            yield tail


# Backwards-compatible alias: the provider is vendor-neutral now, but existing
# imports/tests still reference the old name.
DeepSeekLlmProvider = OpenAiCompatibleLlmProvider


def build_openai_compatible_client(
    api_key: str, base_url: str, timeout_seconds: float, max_retries: int
) -> Any:
    """Construct an OpenAI-compatible async client (DeepSeek or Groq)."""
    from openai import AsyncOpenAI

    return AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout_seconds,
        max_retries=max_retries,
    )


# Backwards-compatible alias.
build_deepseek_client = build_openai_compatible_client
