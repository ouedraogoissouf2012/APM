from functools import lru_cache

from app.core.engines import (
    ENGINE_DEEPSEEK,
    ENGINE_FAKE,
    ENGINE_GROQ,
    ENGINE_GROQ_FALLBACK,
)
from app.domain.exceptions import LlmProviderError
from app.features.conversation.providers.deepseek import (
    OpenAiCompatibleLlmProvider,
    build_openai_compatible_client,
)
from app.features.conversation.providers.fakes import FakeLlm
from app.features.conversation.providers.fallback import FallbackLlmProvider
from app.features.conversation.providers.interfaces import LlmProvider

# The fallback chain's PRIMARY (Groq) must fail FAST and WITHOUT an internal SDK
# retry (#230): a flaky/slow primary is better served by handing off to the
# secondary immediately than by burning the chain's shared deadline
# (fallback.FallbackLlmProvider) on a doomed retry of itself. Deliberately
# shorter/stricter than the shared deepseek_timeout_seconds/max_retries settings
# used for the secondary and for standalone (non-fallback) engine usage.
_FALLBACK_PRIMARY_TIMEOUT_SECONDS = 6.0
_FALLBACK_PRIMARY_MAX_RETRIES = 0


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


def _shared_engine_provider(engine: str, settings: object, max_tokens: int) -> LlmProvider:
    """One cached provider for a single OpenAI-compatible engine."""
    api_key, base_url, model = llm_credentials_for(engine, settings)
    return shared_llm_provider(
        engine=engine,
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout_seconds=settings.deepseek_timeout_seconds,  # type: ignore[attr-defined]
        max_retries=settings.deepseek_max_retries,  # type: ignore[attr-defined]
        max_tokens=max_tokens,
    )


def _fallback_primary_provider(settings: object, max_tokens: int) -> LlmProvider:
    """The fallback chain's PRIMARY (Groq): a short, no-retry client so a flaky
    primary hands off to the secondary quickly (#230) rather than eating the
    chain's shared deadline on itself. A distinct cache entry from any
    standalone (non-fallback) Groq usage, which keeps the shared settings."""
    api_key, base_url, model = llm_credentials_for(ENGINE_GROQ, settings)
    return shared_llm_provider(
        engine=ENGINE_GROQ,
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout_seconds=_FALLBACK_PRIMARY_TIMEOUT_SECONDS,
        max_retries=_FALLBACK_PRIMARY_MAX_RETRIES,
        max_tokens=max_tokens,
    )


def build_feature_llm(engine: str, settings: object, max_tokens: int) -> LlmProvider:
    """The LLM for a feature (conversation, debrief, ...) given its engine.

    "groq_fallback" builds the Groq -> DeepSeek chain (fast + never blocked); any
    other engine is a single cached provider. Fake is handled by the caller."""
    if engine == ENGINE_GROQ_FALLBACK:
        return FallbackLlmProvider(
            [
                _fallback_primary_provider(settings, max_tokens),
                _shared_engine_provider(ENGINE_DEEPSEEK, settings, max_tokens),
            ]
        )
    return _shared_engine_provider(engine, settings, max_tokens)
