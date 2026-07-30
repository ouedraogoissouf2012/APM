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
from pronunciation.core.config import get_settings
from pronunciation.ml.model import Wav2Vec2PhonemeModel

logger = logging.getLogger("pronunciation")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    logger.info("Loading acoustic model %s on %s ...", settings.model_id, settings.device)
    # Heavy load happens here, once. A failure propagates -> process won't start.
    app.state.model = Wav2Vec2PhonemeModel(settings.model_id, device=settings.device)
    logger.info("Acoustic model ready")
    yield
    app.state.model = None


def create_app() -> FastAPI:
    app = FastAPI(title="APM Pronunciation Service", lifespan=lifespan)
    app.include_router(router)
    return app


app = create_app()
