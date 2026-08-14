from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.config import get_settings
from app.core.http.multipart import read_bounded_audio
from app.core.llm.interfaces import SttProvider
from app.core.rate_limit import RateLimiter, user_rate_limit_key
from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.conversation.dependencies import (
    get_conversation_rate_limiter,
    get_stt_provider,
)
from app.features.voice_consent.dependencies import get_voice_consent_service
from app.features.voice_consent.service import VoiceConsentService

router = APIRouter(tags=["conversation"])


class TranscribeOut(BaseModel):
    text: str


@router.post("/transcribe", response_model=TranscribeOut)
async def transcribe(
    request: Request,
    current_user: User = Depends(get_current_user),
    limiter: RateLimiter = Depends(get_conversation_rate_limiter),
    stt: SttProvider = Depends(get_stt_provider),
    consent: VoiceConsentService = Depends(get_voice_consent_service),
) -> TranscribeOut:
    """Transcribe one recorded utterance with the server-side STT (Whisper via
    Groq). Used instead of the browser recognizer for far better accuracy on a
    non-native accent. The uploaded audio is processed in memory and discarded —
    never stored (#128).

    If server-side STT is disabled (STT_ENGINE=device), the get_stt_provider
    dependency resolves to a 404 before this body runs, so that 404 intentionally
    precedes the consent 403: when the feature does not exist for this deployment,
    'not found' is the honest answer regardless of the caller's consent."""
    settings = get_settings()
    await limiter.check(user_rate_limit_key("transcribe", current_user.id))

    # Voice-consent gate (#128): a learner who revoked transcription consent gets a
    # 403 so the client falls back to on-device recognition. Checked BEFORE the
    # multipart body is parsed, so the audio is never read, parsed, or spooled — it
    # is not touched at all (see read_bounded_audio, which parses on demand here).
    if not await consent.may_transcribe(current_user.id):
        raise HTTPException(status_code=403, detail="Transcription consent has been revoked")

    # Reject an oversized upload (#120) and parse fully in memory, never spooled to
    # disk (#227): spool threshold raised to the global body cap, so anything that
    # passed BodySizeLimitMiddleware stays off disk.
    data = await read_bounded_audio(
        request,
        field_name="audio",
        max_bytes=settings.max_upload_bytes,
        spool_max_size=settings.max_request_body_bytes,
    )
    if not data:
        return TranscribeOut(text="")  # silence -> empty, the client stays idle
    text = await stt.transcribe(data)
    return TranscribeOut(text=text)
