import pytest

from app.domain.exceptions import LlmProviderError
from app.features.conversation.factory import build_llm_provider, shared_llm_provider
from app.features.conversation.providers.deepseek import DeepSeekLlmProvider
from app.features.conversation.providers.fakes import FakeLlm


def test_factory_returns_fake_llm_by_default():
    provider = build_llm_provider(engine="fake", api_key="", base_url="", model="m")
    assert isinstance(provider, FakeLlm)


def test_factory_rejects_unknown_engine_instead_of_degrading_to_fake():
    # A typo must fail loudly, never silently serve fake replies in production.
    with pytest.raises(LlmProviderError):
        build_llm_provider(engine="deepsek", api_key="k", base_url="", model="m")


def test_shared_provider_reuses_one_client_per_configuration():
    a = shared_llm_provider(
        engine="deepseek",
        api_key="sk-test",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        timeout_seconds=3.0,
        max_retries=0,
        max_tokens=200,
    )
    b = shared_llm_provider(
        engine="deepseek",
        api_key="sk-test",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        timeout_seconds=3.0,
        max_retries=0,
        max_tokens=200,
    )
    assert a is b  # one AsyncOpenAI client (one connection pool), not one per call


def test_shared_provider_does_not_cache_missing_key_errors():
    kwargs = {
        "engine": "deepseek",
        "api_key": "",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "timeout_seconds": 3.0,
        "max_retries": 0,
        "max_tokens": 201,
    }
    with pytest.raises(LlmProviderError):
        shared_llm_provider(**kwargs)
    # Still raises (not cached as a success) once the key is fixed -> works.
    with pytest.raises(LlmProviderError):
        shared_llm_provider(**kwargs)


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


def test_factory_returns_provider_for_groq_engine():
    # Groq reuses the same OpenAI-compatible provider, just a different base_url /
    # model. It backs the live turn because its time-to-first-token is far lower.
    provider = build_llm_provider(
        engine="groq",
        api_key="gsk-test",
        base_url="https://api.groq.com/openai/v1",
        model="llama-3.3-70b-versatile",
    )
    assert isinstance(provider, DeepSeekLlmProvider)  # the vendor-neutral provider


def test_deepseek_engine_disables_thinking_for_low_latency():
    # DeepSeek flash reasons before answering by default (~14 s TTFT). The factory
    # must disable it so the live chat replies fast (~1.5 s).
    provider = build_llm_provider(
        engine="deepseek",
        api_key="sk",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
    )
    assert provider._extra_body == {"thinking": {"type": "disabled"}}


def test_groq_engine_does_not_send_the_thinking_param():
    # Groq doesn't accept DeepSeek's thinking param — must not be sent.
    provider = build_llm_provider(
        engine="groq",
        api_key="gsk",
        base_url="https://api.groq.com/openai/v1",
        model="llama-3.3-70b-versatile",
    )
    assert provider._extra_body == {}


def test_factory_rejects_groq_without_api_key():
    with pytest.raises(LlmProviderError):
        build_llm_provider(
            engine="groq",
            api_key="",
            base_url="https://api.groq.com/openai/v1",
            model="llama-3.3-70b-versatile",
        )
