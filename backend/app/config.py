from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.engines import (
    ENGINE_DEEPSEEK,
    ENGINE_GOP,
    ENGINE_GROQ,
    ENGINE_GROQ_FALLBACK,
    DebriefEngineName,
    MissionEngineName,
    PronunciationEngineName,
    ShadowingEngineName,
    VoiceEngineName,
)

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
    # A rotated refresh token re-presented within this window is treated as a benign
    # near-simultaneous retry (a network retry, or a second device) — the stale token
    # is rejected but the family is NOT revoked. Beyond it, reuse is a theft signal
    # and revokes every session (#253). Kept short: benign retries land within
    # seconds, while a stolen-token replay is typically minutes/hours later.
    refresh_reuse_grace_seconds: int = 30

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
    mission_rate_limit_max: int = 5
    mission_rate_limit_window_seconds: int = 60
    shadowing_rate_limit_max: int = 20
    shadowing_rate_limit_window_seconds: int = 60

    # Trust X-Forwarded-For for the client IP (#120). Enable ONLY when a trusted
    # reverse proxy sits in front (it sets the header); otherwise a client could
    # forge it to dodge per-IP rate limits. Off by default (direct connections).
    trust_proxy_headers: bool = False
    # Reject an audio upload larger than this before reading it into memory (#120),
    # so a huge/streamed body cannot exhaust the server. 10 MB ~ minutes of speech.
    max_upload_bytes: int = 10 * 1024 * 1024
    # Global request-body ceiling (#221): an ASGI middleware rejects any body larger
    # than this with 413 BEFORE Starlette buffers it, so an unauthenticated multi-GB
    # POST cannot OOM the worker. Kept above max_upload_bytes so a legitimate ~10 MB
    # audio multipart (with its overhead) still passes.
    max_request_body_bytes: int = 12 * 1024 * 1024
    # Redis URL for a cross-instance rate limiter (#120). Empty -> in-memory limiter
    # (single process). Set to redis://host:port/db in a multi-instance deployment.
    redis_url: str = ""

    # Content-addressed TTS cache size (#123): reuse audio for repeated lines
    # (e.g. identical openings). 0 disables the cache.
    tts_cache_max_entries: int = 256
    # Per-turn correction (#123 cost control). Off -> no 2nd LLM call at all.
    # When on, skip utterances shorter than correction_min_words (cheap turns).
    correction_enabled: bool = True
    correction_min_words: int = 3

    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    livekit_token_ttl_seconds: int = 120

    free_tier_daily_minutes: int = 10
    # A session idle longer than this is auto-closed on the user's next start (#119),
    # so an abandoned session (no /end) never locks the user out.
    session_inactivity_timeout_minutes: int = 30
    # A single turn can never bill more than this many minutes of quota, bounding a
    # long client pause between turns.
    session_turn_meter_cap_minutes: float = 5.0

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
    # Only the last N transcript messages are replayed to the LLM each turn (#224):
    # the full transcript is still persisted and the profile memory_summary carries
    # older context, but replaying ALL of it makes cost AND latency grow without
    # bound in a long conversation. 0 = unlimited (no window).
    conversation_history_max_messages: int = 20
    deepseek_debrief_max_tokens: int = 900
    deepseek_mission_max_tokens: int = 500  # a mission brief is short structured JSON
    deepseek_shadowing_max_tokens: int = 300  # a target phrase + short coaching
    debrief_max_errors: int = 5  # errors surfaced to the learner per debrief
    session_history_page_size: int = 20
    # Literal-validated: a typo (e.g. "deepsek") or a not-yet-implemented
    # engine fails at startup instead of silently degrading or 502-ing.
    voice_engine: VoiceEngineName = "fake"  # "fake" (default, no keys) | "deepseek"
    debrief_engine: DebriefEngineName = "fake"  # "fake" (default, no keys) | "deepseek"
    # Compiles a pasted job offer / CV / pitch into a tailored simulation brief.
    mission_engine: MissionEngineName = "fake"  # "fake" (default, no keys) | "deepseek"
    # Generates shadowing target phrases and coaches pronunciation attempts.
    shadowing_engine: ShadowingEngineName = "fake"  # "fake" (default, no keys) | "deepseek"

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
    # Optional Whisper prompt: primes the recognizer with the expected context
    # (a French speaker practising conversational English). It biases decoding
    # toward plausible everyday words without forcing anything — configurable so
    # a scenario can pass domain vocabulary later. Empty disables it.
    groq_stt_prompt: str = "A French speaker is practising everyday spoken English conversation."
    # Groq's LLM for the conversation when VOICE_ENGINE=groq. Llama 3.3 70B keeps
    # DeepSeek-level quality with a much lower time-to-first-token (~0.4 s).
    groq_llm_model: str = "llama-3.3-70b-versatile"

    # Pronunciation scoring (#111 step 2): "fake" (default) makes no phonetic
    # claim; "gop" calls the wav2vec2 pronunciation microservice at gop_service_url.
    # Kept optional so the backend runs standalone without the ML service.
    pronunciation_engine: PronunciationEngineName = "fake"
    gop_service_url: str = "http://localhost:8100"
    gop_timeout_seconds: float = 15.0

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
        engines = (
            self.voice_engine,
            self.debrief_engine,
            self.mission_engine,
            self.shadowing_engine,
        )
        # groq_fallback uses BOTH providers, so it requires both keys.
        needs_deepseek = any(e in (ENGINE_DEEPSEEK, ENGINE_GROQ_FALLBACK) for e in engines)
        needs_groq = any(e in (ENGINE_GROQ, ENGINE_GROQ_FALLBACK) for e in engines)
        if needs_deepseek and not self.deepseek_api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY is required when DeepSeek (or the fallback) is enabled"
            )
        if needs_groq and not self.groq_api_key:
            raise ValueError("GROQ_API_KEY is required when Groq (or the fallback) is enabled")
        if self.pronunciation_engine == ENGINE_GOP and not self.gop_service_url.strip():
            raise ValueError("GOP_SERVICE_URL is required when PRONUNCIATION_ENGINE=gop")

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
