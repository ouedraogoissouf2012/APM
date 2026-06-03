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
    )
    assert isinstance(provider, DeepSeekLlmProvider)
