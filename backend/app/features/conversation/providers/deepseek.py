import logging
import re
from collections.abc import AsyncIterator
from typing import Any

from app.domain.exceptions import LlmProviderError
from app.features.conversation.messages import Message

logger = logging.getLogger(__name__)

# A sentence ends at ., !, or ? possibly followed by closing quotes/brackets.
# We split on this so each streamed chunk is a full, speakable unit for TTS —
# never a half word — while still emitting as early as possible.
_SENTENCE_END = re.compile(r'[.!?]+["\')\]]*')


class DeepSeekLlmProvider:
    """LLM stage backed by DeepSeek's OpenAI-compatible API.

    The async client is injected so the provider is unit-testable without a key.
    Use `deepseek-chat` (V3) for low latency, not the slow reasoner model.
    """

    def __init__(self, client: Any, model: str, max_tokens: int) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    async def complete(self, system_prompt: str, history: list[Message]) -> str:
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        messages += [{"role": m.role, "content": m.content} for m in history]
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=self._max_tokens,
            )
        except Exception as exc:
            logger.warning("DeepSeek provider failed: %s", exc.__class__.__name__)
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
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if not delta:
                    continue
                buffer += delta
                # Emit every complete sentence sitting in the buffer.
                while True:
                    match = _SENTENCE_END.search(buffer)
                    if match is None:
                        break
                    sentence = buffer[: match.end()].strip()
                    buffer = buffer[match.end() :]
                    if sentence:
                        yield sentence
        except Exception as exc:
            logger.warning("DeepSeek stream failed: %s", exc.__class__.__name__)
            raise LlmProviderError("LLM provider failed") from exc
        # Flush any trailing text that did not end with punctuation.
        tail = buffer.strip()
        if tail:
            yield tail


def build_deepseek_client(
    api_key: str, base_url: str, timeout_seconds: float, max_retries: int
) -> Any:
    """Construct the real DeepSeek (OpenAI-compatible) async client."""
    from openai import AsyncOpenAI

    return AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout_seconds,
        max_retries=max_retries,
    )
