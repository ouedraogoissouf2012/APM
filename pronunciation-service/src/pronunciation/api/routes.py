from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile

from pronunciation.api.schemas import PhonemeScoreOut, ScoreOut
from pronunciation.core.concurrency import InferenceGate
from pronunciation.core.config import get_settings
from pronunciation.dependencies import (
    get_inference_gate,
    get_scoring_service,
    require_internal_secret,
)
from pronunciation.ml.transcode import TranscodeError, to_pcm_16k_mono
from pronunciation.services.scoring_service import ScoringService

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/score", response_model=ScoreOut, dependencies=[Depends(require_internal_secret)])
async def score(
    audio: UploadFile,
    target_text: str = Form(...),
    service: ScoringService = Depends(get_scoring_service),
    gate: InferenceGate = Depends(get_inference_gate),
) -> ScoreOut:
    """Score how well each expected phoneme of `target_text` was pronounced in the
    recording. Returns one score per phoneme (GOP, 0..1).

    The scoring (transcode + wav2vec2 inference) is CPU-bound and synchronous, so
    it runs through the InferenceGate: off the event loop (a worker thread) and
    serialised, to keep the server responsive and the cores un-thrashed."""
    settings = get_settings()
    data = await audio.read()

    def _score() -> list:
        # Transcode + inference together on the worker thread: transcode (librosa)
        # is itself blocking, and keeping both under one gated slot bounds the
        # total CPU work per request.
        samples = to_pcm_16k_mono(data, max_bytes=settings.max_audio_bytes)
        return service.score(samples=samples, target_text=target_text)

    try:
        scores = await gate.run(_score)
    except TranscodeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return ScoreOut(
        phonemes=[
            PhonemeScoreOut(phoneme=s.phoneme, score=s.score, start=s.start, end=s.end)
            for s in scores
        ]
    )
