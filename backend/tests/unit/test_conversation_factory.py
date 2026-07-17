import pytest

from app.domain.exceptions import LlmProviderError
from app.features.conversation.factory import build_llm_provider
from app.features.conversation.providers.deepseek import DeepSeekLlmProvider
from app.features.conversation.providers.fakes import FakeLlm


def test_factory_returns_fake_llm_by_default():
    provider = build_llm_provider(engine="fake", api_key="", base_url="", model="m")
    assert isinstance(provider, FakeLlm)


def test_factory_returns_deepseek_when_engine_is_deepseek():
    provider = build_llm_provider(
        engine="deepseek",
        api_key="sk-test",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        timeout_seconds=3.0,
        max_retries=0,
        max_tokens=200,
    )
    assert isinstance(provider, DeepSeekLlmProvider)


def test_factory_rejects_deepseek_without_api_key():
    # Missing key must fail cleanly (LlmProviderError -> 502), not blow up the
    # DI with a raw openai construction error (-> generic 500).
    with pytest.raises(LlmProviderError):
        build_llm_provider(
            engine="deepseek",
            api_key="",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
        )


def test_factory_rejects_deepseek_with_blank_api_key():
    with pytest.raises(LlmProviderError):
        build_llm_provider(
            engine="deepseek",
            api_key="   ",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
        )
