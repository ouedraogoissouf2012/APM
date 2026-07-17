from app.domain.exceptions import LlmProviderError
from app.features.conversation.providers.deepseek import (
    DeepSeekLlmProvider,
    build_deepseek_client,
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
    """Select the LLM provider from config. Defaults to the fake (no keys needed)."""
    if engine == "deepseek":
        if not api_key.strip():
            # Fail cleanly (mapped to 502) instead of letting AsyncOpenAI("")
            # raise a raw error in the DI layer -> generic 500.
            raise LlmProviderError("DeepSeek API key is not configured")
        client = build_deepseek_client(
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
        return DeepSeekLlmProvider(client=client, model=model, max_tokens=max_tokens)
    return FakeLlm()
