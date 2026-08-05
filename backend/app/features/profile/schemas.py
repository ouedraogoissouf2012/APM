from typing import Literal

from pydantic import BaseModel

# Allowed values, mirrored by the mobile dropdowns (profile_screen.dart) and the
# DB defaults (models.py). Kept as named aliases so the API, the correction
# engine, and the accent→locale mapping all agree on the same closed set.
CorrectionIntensity = Literal["gentle", "detailed"]
Accent = Literal["us", "uk"]


class ProfileOut(BaseModel):
    interests: list[str]
    goal: str | None
    correction_intensity: CorrectionIntensity
    accent: Accent
    # What the assistant remembers about the learner across sessions (written by
    # the debrief after each session). Surfaced so the learner can see and edit
    # it — transparency over a value the app already uses in every prompt.
    memory_summary: str

    model_config = {"from_attributes": True}


class ProfileUpdate(BaseModel):
    interests: list[str] | None = None
    goal: str | None = None
    correction_intensity: CorrectionIntensity | None = None
    accent: Accent | None = None
    # Editable so the learner controls what the assistant knows; an empty string
    # clears it. Sanitised server-side (prompt-injection safe) in the service.
    memory_summary: str | None = None
