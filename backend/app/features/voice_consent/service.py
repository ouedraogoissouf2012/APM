"""Voice-consent business logic (#128).

Protective by default, every consent revocable. The record is created lazily on
first read with the safe defaults (transcription on, everything else off)."""

from typing import Any

from app.features.voice_consent.models import VoiceConsent
from app.features.voice_consent.repository import VoiceConsentRepository

# The consents a learner can toggle. Kept as a set so the service rejects any
# unknown field instead of silently setting an arbitrary attribute.
CONSENT_FIELDS = frozenset({"transcription", "scoring", "b2b_share", "model_training"})


class VoiceConsentService:
    def __init__(self, consents: VoiceConsentRepository) -> None:
        self._consents = consents

    async def get_or_create(self, user_id: int) -> VoiceConsent:
        # Delegated to the repository so the first-touch insert is atomic against
        # a concurrent first request (no get-then-create TOCTOU on unique user_id).
        return await self._consents.get_or_create(user_id)

    async def update(self, user_id: int, changes: dict[str, Any]) -> VoiceConsent:
        consent = await self.get_or_create(user_id)
        for field, value in changes.items():
            if field not in CONSENT_FIELDS:
                raise ValueError(f"Unknown consent field: {field!r}")
            setattr(consent, field, bool(value))
        return await self._consents.save(consent)

    async def may_transcribe(self, user_id: int) -> bool:
        """Whether the learner currently allows server-side transcription. A
        missing record means the protective default (transcription on)."""
        transcription, _ = await self.transcription_and_scoring(user_id)
        return transcription

    async def may_score(self, user_id: int) -> bool:
        """Whether the learner currently allows pronunciation/GOP scoring (#419).
        A missing record means the protective default (scoring off)."""
        _, scoring = await self.transcription_and_scoring(user_id)
        return scoring

    async def transcription_and_scoring(self, user_id: int) -> tuple[bool, bool]:
        """One read for both flags so a request that needs both does not hit
        the consent row twice (#419). Missing record = protective defaults."""
        consent = await self._consents.get_by_user_id(user_id)
        if consent is None:
            return True, False
        return consent.transcription, consent.scoring
