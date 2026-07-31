from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.api.client_ip import client_ip
from app.config import get_settings
from app.core.rate_limit import RateLimiter
from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.conversation.dependencies import (
    get_conversation_rate_limiter,
    get_stt_provider,
)
from app.features.conversation.providers.interfaces import SttProvider

router = APIRouter(tags=["conversation"])


class TranscribeOut(BaseModel):
    text: str


@router.post("/transcribe", response_model=TranscribeOut)
async def transcribe(
    request: Request,
    audio: UploadFile,
    current_user: User = Depends(get_current_user),
    limiter: RateLimiter = Depends(get_conversation_rate_limiter),
    stt: SttProvider = Depends(get_stt_provider),
) -> TranscribeOut:
    """Transcribe one recorded utterance with the server-side STT (Whisper via
    Groq). Used instead of the browser recognizer for far better accuracy on a
    non-native accent."""
    settings = get_settings()
    client_host = client_ip(request, settings.trust_proxy_headers)
    await limiter.check(f"transcribe:{client_host}:user:{current_user.id}")

    # Reject an oversized upload (#120). Check the declared Content-Length first so
    # we refuse before reading; the header can be absent or lie, so also enforce on
    # the bytes actually read.
    max_bytes = settings.max_upload_bytes
    declared = request.headers.get("Content-Length")
    if declared is not None and declared.isdigit() and int(declared) > max_bytes:
        raise HTTPException(status_code=413, detail="Audio upload too large")

    data = await audio.read()
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail="Audio upload too large")
    if not data:
        return TranscribeOut(text="")  # silence -> empty, the client stays idle
    text = await stt.transcribe(data)
    return TranscribeOut(text=text)
