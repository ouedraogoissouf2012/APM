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
    # Echo the raw reset token in POST /auth/forgot-password. Tests set this
    # explicitly — NEVER tie it to APP_ENV=test (a deploy with that env would
    # leak tokens and skip production guards). Forbidden in staging/production.
    expose_reset_token: bool = False
    # Optional shared secret for GET /metrics in staging/production. Empty =
    # the route 404s there (dev/test stay open for local scrapes).
    metrics_token: str = ""

    database_url: str
    database_url_test: str = ""
    # Explicit pool sizing (#354): create_async_engine's SQLAlchemy defaults
    # (pool_size=5, max_overflow=10 -> 15 conn/worker) were implicit and
    # undocumented. 10+10 = 20 conn/worker stays well under Postgres's default
    # max_connections=100 for a handful of workers on a single instance; tune
    # both to the actual deployment's worker count and Postgres max_connections.
    db_pool_size: int = 10
    db_max_overflow: int = 10
    # Proactively replace a connection after this many seconds, before a
    # network intermediary (LB, managed-Postgres proxy) or the server itself
    # can silently drop it out from under the pool. Paired with pool_pre_ping
    # (always on, see database.py) which catches what recycling misses.
    db_pool_recycle_seconds: int = 1800  # 30 minutes

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15  # short-lived access token (#239)
    refresh_token_expire_days: int = 30
    # A rotated refresh token re-presented within this window is treated as a benign
    # near-simultaneous retry (a network retry, or a second device) — the stale token
    # is rejected but the family is NOT revoked. Beyond it, reuse is a theft signal
    # and revokes every session (#253). Kept short: benign retries land within
    # seconds, while a stolen-token replay is typically minutes/hours later.
    refresh_reuse_grace_seconds: int = 30
    # How often the in-process background task purges tables with unbounded growth —
    # expired refresh tokens, old idempotency keys, old analytics events (#239/#271).
    # 0 disables the loop (e.g. when an external cron drives the purge instead).
    purge_interval_seconds: int = 6 * 3600  # 6 hours

    login_rate_limit_max: int = 5  # attempts
    login_rate_limit_window_seconds: int = 60
    register_rate_limit_max: int = 5
    register_rate_limit_window_seconds: int = 60
    # Second, coarser limiter keyed by IP ALONE (#355): the (ip, email) limiters
    # above are trivially bypassed by varying the email on every attempt from the
    # same IP, since each new email gets a fresh bucket. This one closes that gap
    # without replacing the fine-grained limiter (which still isolates one email
    # under credential-stuffing from penalizing every other tenant on a shared/NAT
    # IP). Higher ceiling than the per-email limit — it's a coarse abuse backstop,
    # not the primary brute-force guard.
    login_ip_rate_limit_max: int = 30
    login_ip_rate_limit_window_seconds: int = 60
    register_ip_rate_limit_max: int = 30
    register_ip_rate_limit_window_seconds: int = 60
    refresh_rate_limit_max: int = 10
    refresh_rate_limit_window_seconds: int = 60
    # A stolen access token (15 min TTL) but not the password could otherwise
    # brute-force old_password on /auth/password without limit (#300). Keyed by
    # user_id, not IP (the caller is already authenticated) — symmetric to login.
    change_password_rate_limit_max: int = 5
    change_password_rate_limit_window_seconds: int = 900  # 15 minutes
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
    # How many trusted reverse-proxy hops sit directly in front of the app
    # (#383), each APPENDING to X-Forwarded-For (nginx's
    # $proxy_add_x_forwarded_for, AWS ALB, GCP LB — the common case, and what
    # the default of 1 assumes: a single proxy). The real client ends up this
    # many entries from the RIGHT of the header; everything to its left —
    # including the left-most entry client_ip() used to trust — is
    # attacker-suppliable and must be ignored. Only consulted when
    # trust_proxy_headers is True; must be >= 1 in that case (see
    # validate_production_safety) or the header is never trusted at all.
    trusted_proxy_count: int = 1
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
    # Max entries in the in-memory rate limiter's bucket dict. Prevents DoS via
    # high-cardinality keys (e.g., attacker-controlled emails/tokens). Only used
    # when redis_url is empty (in-memory mode); Redis has its own eviction policies.
    rate_limit_max_keys: int = 1000

    # Content-addressed TTS cache size (#123): reuse audio for repeated lines
    # (e.g. identical openings). 0 disables the cache.
    tts_cache_max_entries: int = 256
    # Per-turn correction (#123 cost control). Off -> no 2nd LLM call at all.
    # When on, skip utterances shorter than correction_min_words (cheap turns).
    correction_enabled: bool = True
    correction_min_words: int = 3

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
    # Hard cap on the PERSISTED transcript itself (#364/#379); 0 = unlimited.
    # Without this, a long-running session (unbounded on a paid tier, which has
    # no per-session quota) grows the transcript's JSONB column forever — every
    # turn re-reads and rewrites the WHOLE column. Threaded to
    # ConversationTurnService's transcript_max_messages.
    conversation_transcript_max_messages: int = 200
    deepseek_debrief_max_tokens: int = 900
    deepseek_mission_max_tokens: int = 500  # a mission brief is short structured JSON
    deepseek_shadowing_max_tokens: int = 300  # a target phrase + short coaching
    debrief_max_errors: int = 5  # errors surfaced to the learner per debrief
    # Bounds the debrief prompt to the learner's most recent utterances
    # (#364/#379); 0 = unlimited. Threaded to DebriefAnalyzer's
    # max_learner_turns, reused by both the end-of-session debrief and the
    # onboarding placement (both estimate CEFR from the same analyzer).
    debrief_max_learner_turns: int = 60
    session_history_page_size: int = 20
    # Literal-validated: a typo (e.g. "deepsek") or a not-yet-implemented
    # engine fails at startup instead of silently degrading or 502-ing.
    voice_engine: VoiceEngineName = "fake"  # "fake" (default, no keys) | "deepseek"
    debrief_engine: DebriefEngineName = "fake"  # "fake" (default, no keys) | "deepseek"
    # Compiles a pasted job offer / CV / pitch into a tailored simulation brief.
    mission_engine: MissionEngineName = "fake"  # "fake" (default, no keys) | "deepseek"
    # Generates shadowing target phrases and coaches pronunciation attempts.
    shadowing_engine: ShadowingEngineName = "fake"  # "fake" (default, no keys) | "deepseek"

    # Voice policy (stable for years): CONVERSATION and DRILLS are independent.
    # Conversation defaults to on-device (low latency, works in a browser).
    # Drills (Écho, paires, carnet) use /tts + /transcribe when those engines
    # are on. A single global STT/TTS switch must never disable half the app.
    conversation_stt: Literal["device", "groq"] = "device"
    conversation_tts: Literal["device", "edge"] = "device"
    # /tts (drills). "edge" needs no API key.
    tts_engine: Literal["device", "edge"] = "edge"
    # /transcribe (drills). "auto" = Groq when GROQ_API_KEY is set, else off.
    stt_engine: Literal["device", "groq", "auto"] = "auto"
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
    # Shared secret sent as X-Internal-Secret to the pronunciation microservice
    # (#231). Empty by default (dev/tests, service has no auth configured either);
    # set the SAME value here and as the service's INTERNAL_SECRET to lock it down.
    gop_service_secret: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @property
    def drill_tts_enabled(self) -> bool:
        return self.tts_engine == "edge"

    @property
    def drill_stt_enabled(self) -> bool:
        if self.stt_engine == "device":
            return False
        if self.stt_engine == "groq":
            return bool(self.groq_api_key.strip())
        return bool(self.groq_api_key.strip())  # auto

    @property
    def conversation_stt_on_server(self) -> bool:
        return self.conversation_stt == "groq" and bool(self.groq_api_key.strip())

    @property
    def conversation_tts_on_server(self) -> bool:
        return self.conversation_tts == "edge"

    @model_validator(mode="after")
    def validate_production_safety(self) -> "Settings":
        # Staging is reachable over the network exactly like production (#231): a
        # staging instance left with the example JWT secret (public in this repo)
        # lets anyone forge access tokens. Guard both, not just "production".
        if self.expose_reset_token and self.app_env in ("staging", "production"):
            raise ValueError("EXPOSE_RESET_TOKEN cannot be set in staging/production")
        if self.app_env not in ("staging", "production"):
            return self

        if len(self.jwt_secret.encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET must be at least 32 bytes in production")
        if self.jwt_secret == EXAMPLE_JWT_SECRET:
            raise ValueError("JWT_SECRET must not use the example value in production")
        if "*" in self.cors_origins_list and self.cors_allow_credentials:
            raise ValueError("CORS_ALLOW_ORIGINS=* cannot be used with credentials in production")
        # Both the rate limiter and the TTS cache silently fall back to a
        # single-process in-memory backend when REDIS_URL is empty (#120/#234) —
        # correct in dev/test, but WRONG the moment there's more than one
        # worker/instance: each one gets its own limits/cache instead of a
        # shared one, defeating both (#304).
        if not self.redis_url.strip():
            raise ValueError("REDIS_URL is required in staging/production")
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
        if self.pronunciation_engine == ENGINE_GOP and not self.gop_service_secret.strip():
            raise ValueError("GOP_SERVICE_SECRET is required when PRONUNCIATION_ENGINE=gop")
        # #383: 0 or negative would make client_ip()'s `hops[-trusted_proxy_count]`
        # pick the LEFT-MOST (attacker-controlled) hop again — via Python's
        # `list[-0] == list[0]` for 0, and simply the wrong end for a negative
        # count — silently reopening the exact spoofing bug this setting exists
        # to close. Only checked when the header is actually trusted; an unused
        # value is harmless.
        if self.trust_proxy_headers and self.trusted_proxy_count < 1:
            raise ValueError("TRUSTED_PROXY_COUNT must be >= 1 when TRUST_PROXY_HEADERS is enabled")

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
