from fastapi import APIRouter, Depends

from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.voice_consent.dependencies import get_voice_consent_service
from app.features.voice_consent.schemas import VoiceConsentOut, VoiceConsentUpdate
from app.features.voice_consent.service import VoiceConsentService

router = APIRouter(prefix="/me/voice-consent", tags=["voice-consent"])


@router.get("", response_model=VoiceConsentOut)
async def get_voice_consent(
    current_user: User = Depends(get_current_user),
    service: VoiceConsentService = Depends(get_voice_consent_service),
) -> VoiceConsentOut:
    """The learner's voice consents (created lazily with protective defaults)."""
    consent = await service.get_or_create(current_user.id)
    return VoiceConsentOut.model_validate(consent)


@router.put("", response_model=VoiceConsentOut)
async def update_voice_consent(
    payload: VoiceConsentUpdate,
    current_user: User = Depends(get_current_user),
    service: VoiceConsentService = Depends(get_voice_consent_service),
) -> VoiceConsentOut:
    """Grant or revoke any subset of voice consents. Revoking `transcription`
    means the client must fall back to on-device recognition — the server refuses
    to transcribe (see the /transcribe gate)."""
    consent = await service.update(current_user.id, payload.model_dump(exclude_unset=True))
    return VoiceConsentOut.model_validate(consent)
