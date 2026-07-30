from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile

from pronunciation.api.schemas import PhonemeScoreOut, ScoreOut
from pronunciation.core.config import get_settings
from pronunciation.dependencies import get_scoring_service
from pronunciation.ml.transcode import TranscodeError, to_pcm_16k_mono
from pronunciation.services.scoring_service import ScoringService

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/score", response_model=ScoreOut)
async def score(
    audio: UploadFile,
    target_text: str = Form(...),
    service: ScoringService = Depends(get_scoring_service),
) -> ScoreOut:
    """Score how well each expected phoneme of `target_text` was pronounced in the
    recording. Returns one score per phoneme (GOP, 0..1)."""
    settings = get_settings()
    data = await audio.read()
    try:
        samples = to_pcm_16k_mono(data, max_bytes=settings.max_audio_bytes)
    except TranscodeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    scores = service.score(samples=samples, target_text=target_text)
    return ScoreOut(
        phonemes=[
            PhonemeScoreOut(phoneme=s.phoneme, score=s.score, start=s.start, end=s.end)
            for s in scores
        ]
    )
