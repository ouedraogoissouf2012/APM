from app.features.conversation.providers.deepseek import (
    DeepSeekLlmProvider,
    build_deepseek_client,
)
from app.features.conversation.providers.fakes import FakeLlm
from app.features.conversation.providers.interfaces import LlmProvider


def build_llm_provider(engine: str, api_key: str, base_url: str, model: str) -> LlmProvider:
    """Select the LLM provider from config. Defaults to the fake (no keys needed)."""
    if engine == "deepseek":
        client = build_deepseek_client(api_key=api_key, base_url=base_url)
        return DeepSeekLlmProvider(client=client, model=model)
    return FakeLlm()
