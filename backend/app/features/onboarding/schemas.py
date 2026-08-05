from pydantic import BaseModel, Field


class PlacementIn(BaseModel):
    """The learner's spoken placement answers (already transcribed on the client)
    plus the two profile questions. All optional-ish: an empty `answers` just
    keeps the account's default level."""

    answers: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    goal: str = ""


class PlacementOut(BaseModel):
    cefr_level: str
    interests: list[str]
    goal: str
