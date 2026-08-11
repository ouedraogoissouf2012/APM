from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class SessionStartIn(BaseModel):
    mode: str = Field(pattern="^(scenario|free|mission)$")
    scenario_id: str | None = None
    # Required when mode="mission", forbidden otherwise. Ownership is still
    # re-checked server-side in SessionService.start — this only rejects
    # obviously malformed requests early.
    mission_id: int | None = None

    @model_validator(mode="after")
    def _mission_id_matches_mode(self) -> "SessionStartIn":
        if self.mode == "mission" and self.mission_id is None:
            raise ValueError("mission_id is required when mode is 'mission'")
        if self.mode != "mission" and self.mission_id is not None:
            raise ValueError("mission_id is only allowed when mode is 'mission'")
        return self


class SessionStartOut(BaseModel):
    session_id: int


class SessionOut(BaseModel):
    id: int
    mode: str
    scenario_id: str | None
    duration_minutes: float | None

    model_config = {"from_attributes": True}


class SessionHistoryItemOut(BaseModel):
    id: int
    mode: str
    scenario_id: str | None
    started_at: datetime
    duration_minutes: float | None
    cefr_estimate: str | None

    model_config = {"from_attributes": True}


class TurnOut(BaseModel):
    role: str
    content: str


class ActiveSessionOut(BaseModel):
    """The user's in-progress session plus its transcript so far.

    Lets the mobile app resume a conversation it lost track of (app closed
    without ending, refresh, crash) instead of dead-ending on a 409.
    """

    session_id: int
    mode: str
    scenario_id: str | None
    turns: list[TurnOut]
