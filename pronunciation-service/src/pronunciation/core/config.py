from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed configuration, layered: code defaults -> .env -> environment vars."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    log_level: str = "INFO"

    # Shared-secret auth for /score (#231). The service has no auth of its own and
    # historically bound 0.0.0.0:8100, so anyone reaching the host could call the
    # (CPU-expensive) scoring endpoint for free or DoS it. Empty (default) disables
    # the check — local dev/tests stay frictionless; set it once the backend also
    # sends it (see backend Settings.gop_service_secret) to lock the service down.
    internal_secret: str = ""

    # The phoneme-recognition model (wav2vec2 CTC, espeak/IPA output, Apache 2.0).
    # Loaded once at startup (lifespan). Overridable to pin a version or swap it.
    model_id: str = "facebook/wav2vec2-xlsr-53-espeak-cv-ft"
    # torch device. "cpu" is the safe default; set "cuda" where a GPU exists.
    device: str = "cpu"

    # Language passed to the phonemizer (espeak) for the target text.
    phonemizer_language: str = "en-us"

    # Bound the audio a caller may send, so a huge upload cannot exhaust memory.
    max_audio_bytes: int = 10 * 1024 * 1024  # 10 MB

    # Concurrency control for the CPU-bound inference (see core/concurrency.py).
    # 1 = serialise inferences: the right default for a single CPU instance, where
    # overlapping torch runs over-subscribe the cores and thrash. Raise on a bigger
    # box / GPU. 0 or negative is rejected by InferenceGate.
    max_concurrent_inferences: int = 1
    # Cap torch's intra-op thread pool. 0 = leave torch's default (num cores). With
    # serialised inferences one run may use several threads without contention.
    torch_num_threads: int = 0

    @model_validator(mode="after")
    def require_secret_outside_dev(self) -> "Settings":
        # #424: empty INTERNAL_SECRET is a no-op on /score. Fine in dev/tests;
        # fatal in staging/production so a cloud bind cannot stay open.
        if self.app_env in ("staging", "production") and not self.internal_secret.strip():
            raise ValueError("INTERNAL_SECRET is required when APP_ENV is staging/production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
