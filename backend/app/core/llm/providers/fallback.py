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

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable

from app.core.llm.interfaces import LlmProvider
from app.core.llm.messages import Message
from app.domain.exceptions import LlmProviderError

logger = logging.getLogger(__name__)

# Each provider already has its OWN client-level timeout, but trying them
# sequentially with no cap on the total lets their timeouts STACK — two
# providers at ~20s each can mean ~40s+ before the chain gives up, far past
# what a live conversation can tolerate (#230). This bounds the WHOLE chain
# (every provider attempt combined), regardless of any individual provider's
# own timeout. Once a provider has emitted its first chunk, the deadline no
# longer applies — a turn that has started speaking must never be aborted
# mid-reply (see the streaming caveat below).
_DEFAULT_DEADLINE_SECONDS = 15.0


class FallbackLlmProvider:
    """Wraps an ordered list of LLM providers and fails over between them."""

    def __init__(
        self,
        providers: list[LlmProvider],
        deadline_seconds: float = _DEFAULT_DEADLINE_SECONDS,
        *,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        if not providers:
            raise ValueError("FallbackLlmProvider needs at least one provider")
        self._providers = providers
        self._deadline_seconds = deadline_seconds
        # Injectable monotonic clock: lets a test drive the streaming deadline
        # deterministically instead of relying on sub-100 ms wall-clock timing.
        self._now = now

    async def complete(self, system_prompt: str, history: list[Message]) -> str:
        async def _try_all() -> str:
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

        try:
            return await asyncio.wait_for(_try_all(), timeout=self._deadline_seconds)
        except TimeoutError as exc:
            raise LlmProviderError(
                f"All LLM providers exceeded the {self._deadline_seconds:.0f}s fallback deadline"
            ) from exc

    async def stream_complete(
        self, system_prompt: str, history: list[Message]
    ) -> AsyncIterator[str]:
        deadline = self._now() + self._deadline_seconds
        last_error: Exception | None = None
        for i, provider in enumerate(self._providers):
            remaining = deadline - self._now()
            if remaining <= 0:
                # The deadline is already spent (an earlier provider ate the whole
                # budget) — don't even start another attempt.
                last_error = last_error or LlmProviderError(
                    "Fallback deadline exceeded before every provider was tried"
                )
                break
            emitted = False
            gen = provider.stream_complete(system_prompt, history).__aiter__()
            try:
                while True:
                    if emitted:
                        # Already streaming — never abort a reply in progress.
                        chunk = await gen.__anext__()
                    else:
                        try:
                            chunk = await asyncio.wait_for(gen.__anext__(), timeout=remaining)
                        except TimeoutError as exc:
                            raise LlmProviderError(
                                f"LLM provider timed out after {remaining:.1f}s "
                                "before its first chunk"
                            ) from exc
                    emitted = True
                    yield chunk
            except StopAsyncIteration:
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
