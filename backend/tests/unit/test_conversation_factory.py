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


class _FakeSettings:
    groq_api_key = "gsk-test"
    groq_base_url = "https://api.groq.com/openai/v1"
    groq_llm_model = "llama-3.3-70b-versatile"
    deepseek_api_key = "sk-test"
    deepseek_base_url = "https://api.deepseek.com"
    deepseek_model = "deepseek-v4-flash"
    deepseek_timeout_seconds = 20.0
    deepseek_max_retries = 1


def test_groq_fallback_builds_a_two_provider_fallback_chain():
    from app.features.conversation.factory import build_feature_llm
    from app.features.conversation.providers.fallback import FallbackLlmProvider

    provider = build_feature_llm("groq_fallback", _FakeSettings(), max_tokens=300)

    assert isinstance(provider, FallbackLlmProvider)
    assert len(provider._providers) == 2


def test_groq_fallback_primary_is_short_and_no_retry_distinct_from_standalone_groq():
    # #230: the fallback chain's PRIMARY (Groq) must fail fast (short timeout, no
    # internal SDK retry) so the secondary gets a fair share of the chain's
    # deadline — a distinct client/cache entry from standalone (non-fallback)
    # Groq usage, which keeps the shared deepseek_timeout_seconds/max_retries.
    from app.features.conversation.factory import (
        _FALLBACK_PRIMARY_MAX_RETRIES,
        _FALLBACK_PRIMARY_TIMEOUT_SECONDS,
        build_feature_llm,
        shared_llm_provider,
    )

    settings = _FakeSettings()
    fallback_provider = build_feature_llm("groq_fallback", settings, max_tokens=300)
    primary = fallback_provider._providers[0]
    standalone_groq = build_feature_llm("groq", settings, max_tokens=300)

    # Different timeout/retries -> a different lru_cache entry -> not the same client.
    assert primary is not standalone_groq
    expected_primary = shared_llm_provider(
        engine="groq",
        api_key=settings.groq_api_key,
        base_url=settings.groq_base_url,
        model=settings.groq_llm_model,
        timeout_seconds=_FALLBACK_PRIMARY_TIMEOUT_SECONDS,
        max_retries=_FALLBACK_PRIMARY_MAX_RETRIES,
        max_tokens=300,
    )
    assert primary is expected_primary
    assert _FALLBACK_PRIMARY_MAX_RETRIES == 0
    assert settings.deepseek_timeout_seconds > _FALLBACK_PRIMARY_TIMEOUT_SECONDS


def test_groq_fallback_secondary_keeps_the_shared_deepseek_settings():
    # The secondary (DeepSeek) is the reliable safety net — it keeps the normal,
    # shared timeout/retries rather than the primary's fast-fail tuning.
    from app.features.conversation.factory import build_feature_llm, shared_llm_provider

    settings = _FakeSettings()
    fallback_provider = build_feature_llm("groq_fallback", settings, max_tokens=300)
    secondary = fallback_provider._providers[1]

    expected_secondary = shared_llm_provider(
        engine="deepseek",
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        timeout_seconds=settings.deepseek_timeout_seconds,
        max_retries=settings.deepseek_max_retries,
        max_tokens=300,
    )
    assert secondary is expected_secondary
