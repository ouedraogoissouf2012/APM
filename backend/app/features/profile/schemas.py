from typing import Annotated, Literal

from pydantic import BaseModel, Field

# Allowed values, mirrored by the mobile dropdowns (profile_screen.dart) and the
# DB defaults (models.py). Kept as named aliases so the API, the correction
# engine, and the accent→locale mapping all agree on the same closed set.
CorrectionIntensity = Literal["gentle", "detailed"]
Accent = Literal["us", "uk"]

# Bounds on the free-form profile fields (#233). Without them, `interests` is an
# unbounded JSONB blob and `goal` could exceed its String(500) column (a 500 on
# write). Upper bounds only — every previously valid input still passes.
MAX_INTERESTS = 20
MAX_INTEREST_LENGTH = 50
MAX_GOAL_LENGTH = 500  # matches LearnerProfile.goal String(500)

Interest = Annotated[str, Field(max_length=MAX_INTEREST_LENGTH)]


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
    interests: list[Interest] | None = Field(default=None, max_length=MAX_INTERESTS)
    goal: str | None = Field(default=None, max_length=MAX_GOAL_LENGTH)
    correction_intensity: CorrectionIntensity | None = None
    accent: Accent | None = None
    # Editable so the learner controls what the assistant knows; an empty string
    # clears it. Sanitised server-side (prompt-injection safe) in the service.
    memory_summary: str | None = None
