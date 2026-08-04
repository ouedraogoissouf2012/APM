"""A fallback chain of LLM providers (the Groq -> DeepSeek safety net).

Tries each provider in order; on failure, moves to the next. This gives the app
the best of both: Groq's low, stable latency for free during the day, and
DeepSeek's unlimited paid capacity as a safety net when Groq is rate-limited (429)
or otherwise unavailable — so a turn never dies.

The conversation history is engine-neutral (stored as text in the transcript and
replayed to whichever provider serves the turn), so the takeover is seamless: the
secondary receives exactly the same messages the primary did.

Streaming rule: fall back ONLY if a provider fails BEFORE its first chunk. Once a
chunk has streamed to the client, we cannot un-send it, so a later failure ends
the turn rather than restarting on the next provider (which would duplicate text).
"""

import logging
from collections.abc import AsyncIterator

from app.domain.exceptions import LlmProviderError
from app.features.conversation.messages import Message
from app.features.conversation.providers.interfaces import LlmProvider

logger = logging.getLogger(__name__)


class FallbackLlmProvider:
    """Wraps an ordered list of LLM providers and fails over between them."""

    def __init__(self, providers: list[LlmProvider]) -> None:
        if not providers:
            raise ValueError("FallbackLlmProvider needs at least one provider")
        self._providers = providers

    async def complete(self, system_prompt: str, history: list[Message]) -> str:
        last_error: Exception | None = None
        for i, provider in enumerate(self._providers):
            try:
                return await provider.complete(system_prompt, history)
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "LLM provider %d/%d failed (%s); trying next",
                    i + 1,
                    len(self._providers),
                    exc.__class__.__name__,
                )
        raise LlmProviderError("All LLM providers failed") from last_error

    async def stream_complete(
        self, system_prompt: str, history: list[Message]
    ) -> AsyncIterator[str]:
        last_error: Exception | None = None
        for i, provider in enumerate(self._providers):
            emitted = False
            try:
                async for chunk in provider.stream_complete(system_prompt, history):
                    emitted = True
                    yield chunk
                return  # provider finished cleanly
            except Exception as exc:
                if emitted:
                    # Already streamed part of this reply to the client — cannot
                    # switch providers now without garbling it. End the turn.
                    raise
                last_error = exc
                logger.warning(
                    "LLM stream provider %d/%d failed before first chunk (%s); trying next",
                    i + 1,
                    len(self._providers),
                    exc.__class__.__name__,
                )
        raise LlmProviderError("All LLM providers failed") from last_error
