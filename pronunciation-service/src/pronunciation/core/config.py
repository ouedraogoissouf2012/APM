from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed configuration, layered: code defaults -> .env -> environment vars."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    log_level: str = "INFO"

    # The phoneme-recognition model (wav2vec2 CTC, espeak/IPA output, Apache 2.0).
    # Loaded once at startup (lifespan). Overridable to pin a version or swap it.
    model_id: str = "facebook/wav2vec2-xlsr-53-espeak-cv-ft"
    # torch device. "cpu" is the safe default; set "cuda" where a GPU exists.
    device: str = "cpu"

    # Language passed to the phonemizer (espeak) for the target text.
    phonemizer_language: str = "en-us"

    # Bound the audio a caller may send, so a huge upload cannot exhaust memory.
    max_audio_bytes: int = 10 * 1024 * 1024  # 10 MB


@lru_cache
def get_settings() -> Settings:
    return Settings()
