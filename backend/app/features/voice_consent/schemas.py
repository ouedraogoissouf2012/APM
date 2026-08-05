from pydantic import BaseModel


class VoiceConsentOut(BaseModel):
    transcription: bool
    scoring: bool
    b2b_share: bool
    model_training: bool

    model_config = {"from_attributes": True}


class VoiceConsentUpdate(BaseModel):
    # All optional: a PUT updates only the consents it names, leaving the rest.
    transcription: bool | None = None
    scoring: bool | None = None
    b2b_share: bool | None = None
    model_training: bool | None = None
