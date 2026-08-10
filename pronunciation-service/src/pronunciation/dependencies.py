"""Dependency injection: expose the singleton acoustic model (loaded once in the
lifespan handler, stored on app.state) as a ScoringService to the routes."""

import hmac

from fastapi import Depends, Header, HTTPException, Request, status

from pronunciation.core.concurrency import InferenceGate
from pronunciation.core.config import get_settings
from pronunciation.ml.model import PhonemeAcousticModel
from pronunciation.services.scoring_service import ScoringService


def require_internal_secret(x_internal_secret: str | None = Header(default=None)) -> None:
    """Guard /score with a shared secret (#231): the service has no other auth and
    used to bind 0.0.0.0, so any host reaching the port could run (CPU-expensive)
    inference for free or DoS it. A no-op when unconfigured (dev/tests) so nothing
    breaks until the backend is also wired to send the header.

    Constant-time comparison: a naive `==` leaks the secret's length/prefix through
    response-time differences (timing side-channel) on a network-reachable check."""
    expected = get_settings().internal_secret
    if not expected:
        return
    if x_internal_secret is None or not hmac.compare_digest(x_internal_secret, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing credentials"
        )


def get_model(request: Request) -> PhonemeAcousticModel:
    model = getattr(request.app.state, "model", None)
    if model is None:  # pragma: no cover - lifespan guarantees it in normal runs
        raise RuntimeError("Acoustic model not loaded")
    return model


def get_inference_gate(request: Request) -> InferenceGate:
    gate = getattr(request.app.state, "inference_gate", None)
    if gate is None:  # pragma: no cover - lifespan guarantees it in normal runs
        raise RuntimeError("Inference gate not initialised")
    return gate


def get_scoring_service(
    model: PhonemeAcousticModel = Depends(get_model),
) -> ScoringService:
    return ScoringService(model=model)
