"""Unit tests for the voice-consent service (#128)."""

import pytest

from app.features.voice_consent.models import VoiceConsent
from app.features.voice_consent.service import VoiceConsentService


class _InMemoryConsentRepo:
    def __init__(self) -> None:
        self._by_user: dict[int, VoiceConsent] = {}
        self._seq = 0

    async def get_by_user_id(self, user_id):
        return self._by_user.get(user_id)

    async def create(self, consent):
        self._seq += 1
        consent.id = self._seq
        # Model column defaults only apply on DB flush; set them here so the
        # in-memory fake mirrors the protective defaults.
        consent.transcription = True if consent.transcription is None else consent.transcription
        for f in ("scoring", "b2b_share", "model_training"):
            if getattr(consent, f) is None:
                setattr(consent, f, False)
        self._by_user[consent.user_id] = consent
        return consent

    async def save(self, consent):
        self._by_user[consent.user_id] = consent
        return consent


def _service():
    return VoiceConsentService(_InMemoryConsentRepo())


@pytest.mark.asyncio
async def test_defaults_are_protective():
    consent = await _service().get_or_create(user_id=1)
    assert consent.transcription is True  # app works out of the box
    assert consent.scoring is False
    assert consent.b2b_share is False
    assert consent.model_training is False


@pytest.mark.asyncio
async def test_get_or_create_is_idempotent():
    service = _service()
    a = await service.get_or_create(1)
    b = await service.get_or_create(1)
    assert a is b


@pytest.mark.asyncio
async def test_can_grant_an_opt_in_consent():
    service = _service()
    consent = await service.update(1, {"scoring": True})
    assert consent.scoring is True
    assert consent.transcription is True  # untouched


@pytest.mark.asyncio
async def test_can_revoke_transcription():
    service = _service()
    consent = await service.update(1, {"transcription": False})
    assert consent.transcription is False


@pytest.mark.asyncio
async def test_unknown_consent_field_is_rejected():
    service = _service()
    with pytest.raises(ValueError):
        await service.update(1, {"sell_my_voice": True})


@pytest.mark.asyncio
async def test_may_transcribe_defaults_true_without_a_record():
    service = _service()
    assert await service.may_transcribe(999) is True


@pytest.mark.asyncio
async def test_may_transcribe_reflects_revocation():
    service = _service()
    await service.update(1, {"transcription": False})
    assert await service.may_transcribe(1) is False
