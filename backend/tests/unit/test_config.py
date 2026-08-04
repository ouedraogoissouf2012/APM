import pytest
from pydantic import ValidationError

from app.config import EXAMPLE_JWT_SECRET, Settings


def _settings(**overrides: object) -> Settings:
    defaults = {
        "database_url": "postgresql+asyncpg://user:pass@localhost:5432/app",
        "jwt_secret": "dev-secret",
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def test_dev_allows_fake_engines_and_example_style_config():
    settings = _settings(
        app_env="dev",
        cors_allow_origins="*",
        cors_allow_credentials=True,
        voice_engine="fake",
        debrief_engine="fake",
    )

    assert settings.app_env == "dev"
    assert settings.cors_origins_list == ["*"]


def test_rejects_unknown_voice_engine_at_startup():
    # A typo must fail at startup, not silently degrade to the fake engine.
    with pytest.raises(ValidationError):
        _settings(voice_engine="deepsek")


def test_rejects_not_implemented_livekit_engine_at_startup():
    # "livekit" is reserved for the realtime engine (#69). Until it exists,
    # configuring it must fail at startup instead of 502-ing on every turn.
    with pytest.raises(ValidationError):
        _settings(voice_engine="livekit")


def test_production_rejects_weak_jwt_secret():
    with pytest.raises(ValidationError, match="JWT_SECRET must be at least 32 bytes"):
        _settings(app_env="production", jwt_secret="too-short")


def test_production_rejects_example_jwt_secret():
    with pytest.raises(ValidationError, match="JWT_SECRET must not use the example value"):
        _settings(app_env="production", jwt_secret=EXAMPLE_JWT_SECRET)


def test_production_rejects_wildcard_cors_with_credentials():
    with pytest.raises(ValidationError, match=r"CORS_ALLOW_ORIGINS=\*"):
        _settings(
            app_env="production",
            jwt_secret="a-secure-production-secret-32-bytes",
            cors_allow_origins="https://app.example.com,*",
            cors_allow_credentials=True,
        )


def test_production_rejects_deepseek_without_api_key():
    with pytest.raises(ValidationError, match="DEEPSEEK_API_KEY is required"):
        _settings(
            app_env="production",
            jwt_secret="a-secure-production-secret-32-bytes",
            cors_allow_origins="https://app.example.com",
            voice_engine="deepseek",
            debrief_engine="fake",
            deepseek_api_key="",
        )


def test_production_allows_deepseek_with_safe_config():
    settings = _settings(
        app_env="production",
        jwt_secret="a-secure-production-secret-32-bytes",
        cors_allow_origins="https://app.example.com",
        voice_engine="deepseek",
        debrief_engine="deepseek",
        deepseek_api_key="sk-test",
    )

    assert settings.app_env == "production"


def test_production_rejects_gop_engine_without_service_url():
    with pytest.raises(ValidationError, match="GOP_SERVICE_URL is required"):
        _settings(
            app_env="production",
            jwt_secret="a-secure-production-secret-32-bytes",
            cors_allow_origins="https://app.example.com",
            pronunciation_engine="gop",
            gop_service_url="",
        )


def test_production_allows_gop_engine_with_service_url():
    settings = _settings(
        app_env="production",
        jwt_secret="a-secure-production-secret-32-bytes",
        cors_allow_origins="https://app.example.com",
        pronunciation_engine="gop",
        gop_service_url="http://pronunciation:8100",
    )

    assert settings.pronunciation_engine == "gop"


def test_production_requires_both_keys_for_groq_fallback():
    # The fallback uses Groq AND DeepSeek, so production needs both keys.
    with pytest.raises(ValidationError, match="GROQ_API_KEY is required"):
        _settings(
            app_env="production",
            jwt_secret="a-secure-production-secret-32-bytes",
            cors_allow_origins="https://app.example.com",
            voice_engine="groq_fallback",
            deepseek_api_key="sk-test",
            groq_api_key="",
        )
    with pytest.raises(ValidationError, match="DEEPSEEK_API_KEY is required"):
        _settings(
            app_env="production",
            jwt_secret="a-secure-production-secret-32-bytes",
            cors_allow_origins="https://app.example.com",
            voice_engine="groq_fallback",
            deepseek_api_key="",
            groq_api_key="gsk-test",
        )


def test_production_allows_groq_fallback_with_both_keys():
    settings = _settings(
        app_env="production",
        jwt_secret="a-secure-production-secret-32-bytes",
        cors_allow_origins="https://app.example.com",
        voice_engine="groq_fallback",
        deepseek_api_key="sk-test",
        groq_api_key="gsk-test",
    )
    assert settings.voice_engine == "groq_fallback"
