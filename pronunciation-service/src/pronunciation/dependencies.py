"""Dependency injection: expose the singleton acoustic model (loaded once in the
lifespan handler, stored on app.state) as a ScoringService to the routes."""

from fastapi import Depends, Request

from pronunciation.ml.model import PhonemeAcousticModel
from pronunciation.services.scoring_service import ScoringService


def get_model(request: Request) -> PhonemeAcousticModel:
    model = getattr(request.app.state, "model", None)
    if model is None:  # pragma: no cover - lifespan guarantees it in normal runs
        raise RuntimeError("Acoustic model not loaded")
    return model


def get_scoring_service(
    model: PhonemeAcousticModel = Depends(get_model),
) -> ScoringService:
    return ScoringService(model=model)
