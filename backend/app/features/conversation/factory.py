from functools import lru_cache

from app.core.engines import ENGINE_DEEPSEEK, ENGINE_FAKE, ENGINE_GROQ
from app.domain.exceptions import LlmProviderError
from app.features.conversation.providers.deepseek import (
    OpenAiCompatibleLlmProvider,
    build_openai_compatible_client,
)
from app.features.conversation.providers.fakes import FakeLlm
from app.features.conversation.providers.interfaces import LlmProvider


def build_llm_provider(
    engine: str,
    api_key: str,
    base_url: str,
    model: str,
    timeout_seconds: float = 20.0,
    max_retries: int = 1,
    max_tokens: int = 400,
) -> LlmProvider:
    """Select the LLM provider from config.

    Unknown engines raise instead of silently degrading to the fake provider —
    settings validate the engine names (Literal), this is defense in depth.
    """
    if engine == ENGINE_FAKE:
        return FakeLlm()
    if engine in (ENGINE_DEEPSEEK, ENGINE_GROQ):
        # Both are OpenAI-compatible: same provider, only the injected client's
        # base_url and the model differ (Groq = faster time-to-first-token).
        if not api_key.strip():
            # Fail cleanly (mapped to 502) instead of letting AsyncOpenAI("")
            # raise a raw error in the DI layer -> generic 500.
            raise LlmProviderError(f"{engine} API key is not configured")
        client = build_openai_compatible_client(
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
        # DeepSeek flash reasons before answering by default (~14 s to first token);
        # disable it for a live chat -> ~1.5 s. Groq has no such param.
        extra_body = {"thinking": {"type": "disabled"}} if engine == ENGINE_DEEPSEEK else None
        return OpenAiCompatibleLlmProvider(
            client=client, model=model, max_tokens=max_tokens, extra_body=extra_body
        )
    raise LlmProviderError(f"Unsupported LLM engine: {engine!r}")


# Process-wide provider cache: one AsyncOpenAI client (one connection pool) per
# configuration, instead of a new client per HTTP request. Errors (e.g. missing
# API key) are not cached — lru_cache only stores successful results.
shared_llm_provider = lru_cache(maxsize=8)(build_llm_provider)


def llm_credentials_for(engine: str, settings: object) -> tuple[str, str, str]:
    """The (api_key, base_url, model) an OpenAI-compatible engine needs, from
    settings. One place so every feature (conversation, debrief, mission,
    shadowing) picks Groq vs DeepSeek credentials consistently — no duplication."""
    if engine == ENGINE_GROQ:
        return (
            settings.groq_api_key,  # type: ignore[attr-defined]
            settings.groq_base_url,  # type: ignore[attr-defined]
            settings.groq_llm_model,  # type: ignore[attr-defined]
        )
    return (
        settings.deepseek_api_key,  # type: ignore[attr-defined]
        settings.deepseek_base_url,  # type: ignore[attr-defined]
        settings.deepseek_model,  # type: ignore[attr-defined]
    )
