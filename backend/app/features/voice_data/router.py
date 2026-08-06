from fastapi import APIRouter, Depends

from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.voice_data.dependencies import get_voice_data_service
from app.features.voice_data.schemas import VoiceDataEraseOut, VoiceDataExportOut
from app.features.voice_data.service import VoiceDataService

router = APIRouter(prefix="/me/voice-data", tags=["voice-data"])


@router.post("/export", response_model=VoiceDataExportOut)
async def export_voice_data(
    current_user: User = Depends(get_current_user),
    service: VoiceDataService = Depends(get_voice_data_service),
) -> VoiceDataExportOut:
    """Export the learner's voice-derived data: utterances, vocabulary, debriefs,
    and review items. Raw audio is never retained, so it is not — and cannot be —
    part of the export."""
    export = await service.export(current_user.id)
    return VoiceDataExportOut(
        raw_audio_retained=export.raw_audio_retained,
        utterances=export.utterances,
        vocabulary=export.vocabulary,
        debriefs=export.debriefs,
        review_items=export.review_items,
    )


@router.delete("", response_model=VoiceDataEraseOut)
async def erase_voice_data(
    current_user: User = Depends(get_current_user),
    service: VoiceDataService = Depends(get_voice_data_service),
) -> VoiceDataEraseOut:
    """Erase the learner's voice-derived data: transcripts, debriefs, the session
    records, vocabulary, review items, compiled missions, per-session analytics
    events, the profile memory summary, the speech-derived user fields (CEFR level
    and streak counters, reset to defaults), and the cached turn replies. The
    account, login, consent record, and onboarding settings are kept — this is data
    erasure, not account deletion."""
    deleted = await service.erase(current_user.id)
    return VoiceDataEraseOut(deleted=deleted)
