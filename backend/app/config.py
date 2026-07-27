from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.engines import ENGINE_DEEPSEEK, DebriefEngineName, VoiceEngineName

EXAMPLE_JWT_SECRET = "change-me-in-production-use-a-long-random-string"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    app_env: Literal["dev", "test", "staging", "production"] = Field(
        default="dev",
        validation_alias=AliasChoices("APP_ENV", "ENV"),
    )

    database_url: str
    database_url_test: str = ""

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60  # short-lived access token
    refresh_token_expire_days: int = 30

    login_rate_limit_max: int = 5  # attempts
    login_rate_limit_window_seconds: int = 60
    register_rate_limit_max: int = 5
    register_rate_limit_window_seconds: int = 60
    refresh_rate_limit_max: int = 10
    refresh_rate_limit_window_seconds: int = 60
    conversation_rate_limit_max: int = 20
    conversation_rate_limit_window_seconds: int = 60
    debrief_rate_limit_max: int = 5
    debrief_rate_limit_window_seconds: int = 60

    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    livekit_token_ttl_seconds: int = 120

    free_tier_daily_minutes: int = 10

    log_level: str = "INFO"
    # Comma-separated list of allowed CORS origins ("*" = all, dev only).
    cors_allow_origins: str = "*"
    cors_allow_credentials: bool = True

    # Conversation / voice
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"  # V4 fast tier (deepseek-chat was retired)
    deepseek_timeout_seconds: float = 20.0
    deepseek_max_retries: int = 1
    deepseek_conversation_max_tokens: int = 400
    deepseek_debrief_max_tokens: int = 900
    debrief_max_errors: int = 5  # errors surfaced to the learner per debrief
    session_history_page_size: int = 20
    # Literal-validated: a typo (e.g. "deepsek") or a not-yet-implemented
    # engine fails at startup instead of silently degrading or 502-ing.
    voice_engine: VoiceEngineName = "fake"  # "fake" (default, no keys) | "deepseek"
    debrief_engine: DebriefEngineName = "fake"  # "fake" (default, no keys) | "deepseek"

    # Text-to-speech: "device" = on-device system voice (default, robotic);
    # "edge" = free Microsoft Edge neural voices synthesized server-side and
    # streamed to the client (no key). Voice is chosen from the learner's accent.
    tts_engine: Literal["device", "edge"] = "device"

    # Speech-to-text: "device" = browser recognition (default, weak on accents);
    # "groq" = Whisper via Groq (free API key), recorded on the device and
    # transcribed server-side — far better for a non-native accent.
    stt_engine: Literal["device", "groq"] = "device"
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_stt_model: str = "whisper-large-v3-turbo"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def validate_production_safety(self) -> "Settings":
        if self.app_env != "production":
            return self

        if len(self.jwt_secret.encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET must be at least 32 bytes in production")
        if self.jwt_secret == EXAMPLE_JWT_SECRET:
            raise ValueError("JWT_SECRET must not use the example value in production")
        if "*" in self.cors_origins_list and self.cors_allow_credentials:
            raise ValueError("CORS_ALLOW_ORIGINS=* cannot be used with credentials in production")
        if (
            ENGINE_DEEPSEEK in (self.voice_engine, self.debrief_engine)
            and not self.deepseek_api_key
        ):
            raise ValueError("DEEPSEEK_API_KEY is required when DeepSeek is enabled")

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
