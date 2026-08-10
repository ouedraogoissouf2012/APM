from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

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
from app.features.voice_consent.dependencies import get_voice_consent_service
from app.features.voice_consent.service import VoiceConsentService

router = APIRouter(tags=["conversation"])


class TranscribeOut(BaseModel):
    text: str


class _InMemoryMultiPartParser(MultiPartParser):
    """A multipart parser that keeps every part in memory instead of spooling it
    to a real temp FILE on disk.

    Starlette's default parser writes each part to a ``SpooledTemporaryFile`` that
    rolls to disk once it passes ``spool_max_size`` (1 MB). A ~40 s recorded turn
    (~1.3 MB) therefore transiently lands on disk BEFORE the endpoint runs — which
    undercuts the "audio is processed in memory and never stored on disk" promise
    of #128 (#227). Raising the spool threshold to the global body cap (already
    enforced by BodySizeLimitMiddleware) keeps anything that reaches the endpoint
    in the in-memory buffer, so a legitimate clip never touches disk.

    Couples to Starlette's internal ``spool_max_size`` / ``max_part_size`` class
    attributes (set per-instance here); revisit on a Starlette upgrade — tracked.
    """

    def __init__(self, *args: object, spool_max_size: int, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        # ints, not floats — SpooledTemporaryFile(max_size=...) expects an int.
        self.spool_max_size = spool_max_size
        self.max_part_size = spool_max_size


async def _read_audio_bytes(request: Request, spool_max_size: int) -> bytes:
    """Read the uploaded ``audio`` part fully in memory (never spooled to disk).

    Parsing happens here, in the endpoint body, so it runs AFTER the consent gate:
    a learner who revoked consent has their audio neither read nor parsed at all.
    """
    parser = _InMemoryMultiPartParser(
        request.headers, request.stream(), spool_max_size=spool_max_size
    )
    try:
        form = await parser.parse()
    except MultiPartException:
        raise HTTPException(status_code=422, detail="Malformed multipart upload") from None
    # NB: the parser yields Starlette's UploadFile, NOT fastapi.UploadFile (a
    # subclass) — this isinstance must be against the Starlette one to match.
    upload = form.get("audio")
    if not isinstance(upload, UploadFile):
        raise HTTPException(status_code=422, detail="Missing 'audio' file part")
    try:
        return await upload.read()
    finally:
        await upload.close()


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
    client_host = client_ip(request, settings.trust_proxy_headers)
    await limiter.check(f"transcribe:{client_host}:user:{current_user.id}")

    # Voice-consent gate (#128): a learner who revoked transcription consent gets a
    # 403 so the client falls back to on-device recognition. Checked BEFORE the
    # multipart body is parsed, so the audio is never read, parsed, or spooled — it
    # is not touched at all (see _read_audio_bytes, which parses on demand here).
    if not await consent.may_transcribe(current_user.id):
        raise HTTPException(status_code=403, detail="Transcription consent has been revoked")

    # Reject an oversized upload (#120). Check the declared Content-Length first so
    # we refuse before reading; the header can be absent or lie, so also enforce on
    # the bytes actually read.
    max_bytes = settings.max_upload_bytes
    declared = request.headers.get("Content-Length")
    if declared is not None and declared.isdigit() and int(declared) > max_bytes:
        raise HTTPException(status_code=413, detail="Audio upload too large")

    # Parse the upload fully in memory (#227): spool threshold raised to the global
    # body cap, so anything that passed BodySizeLimitMiddleware stays off disk.
    data = await _read_audio_bytes(request, settings.max_request_body_bytes)
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail="Audio upload too large")
    if not data:
        return TranscribeOut(text="")  # silence -> empty, the client stays idle
    text = await stt.transcribe(data)
    return TranscribeOut(text=text)
