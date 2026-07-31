"""Pronunciation scoring microservice — phoneme-level GOP via wav2vec2.

The ~1 GB acoustic model is loaded ONCE in the lifespan handler and stored on
app.state, so the first request doesn't pay the load cost and all requests share
one instance (singleton). If the model fails to load, lifespan raises and the
process exits — fail fast, let the orchestrator restart, never serve degraded.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from pronunciation.api.routes import router
from pronunciation.core.concurrency import InferenceGate
from pronunciation.core.config import get_settings
from pronunciation.ml.domain import TARGET_SAMPLE_RATE
from pronunciation.ml.model import Wav2Vec2PhonemeModel

logger = logging.getLogger("pronunciation")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    # Bound torch's thread pool before any inference, so serialised runs don't
    # over-subscribe the CPU. 0 leaves torch's default.
    if settings.torch_num_threads > 0:
        import torch

        torch.set_num_threads(settings.torch_num_threads)

    logger.info("Loading acoustic model %s on %s ...", settings.model_id, settings.device)
    # Heavy load happens here, once. A failure propagates -> process won't start.
    model = Wav2Vec2PhonemeModel(settings.model_id, device=settings.device)
    # Warm up torch's kernels with throwaway inferences so the FIRST real request
    # doesn't pay the cold-start cost. torch (on CPU) specialises kernels per input
    # LENGTH, so we warm a few representative durations (1-4 s of speech) rather
    # than a single one. A warm-up failure is non-fatal — the first request is just
    # slower.
    try:
        for seconds in (1, 2, 3, 4):
            model.emission_log_probs([0.0] * (TARGET_SAMPLE_RATE * seconds))
        logger.info("Warm-up inference done")
    except Exception:
        logger.warning("Warm-up inference failed; first request will be slower", exc_info=True)
    app.state.model = model
    # One gate per process: serialises + off-loads the CPU-bound inference so it
    # never blocks the event loop and never thrashes the cores.
    app.state.inference_gate = InferenceGate(settings.max_concurrent_inferences)
    logger.info("Acoustic model ready (max_concurrent=%d)", settings.max_concurrent_inferences)
    yield
    app.state.model = None


def create_app() -> FastAPI:
    app = FastAPI(title="APM Pronunciation Service", lifespan=lifespan)
    app.include_router(router)
    return app


app = create_app()
