from fastapi import APIRouter, Depends, Request, UploadFile
from pydantic import BaseModel

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
    client_host = request.client.host if request.client else "anonymous"
    await limiter.check(f"transcribe:{client_host}:user:{current_user.id}")
    data = await audio.read()
    if not data:
        return TranscribeOut(text="")  # silence -> empty, the client stays idle
    text = await stt.transcribe(data)
    return TranscribeOut(text=text)
