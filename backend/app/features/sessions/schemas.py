from datetime import datetime

from pydantic import BaseModel, Field


class SessionStartIn(BaseModel):
    mode: str = Field(pattern="^(scenario|free)$")
    scenario_id: str | None = None


class SessionStartOut(BaseModel):
    session_id: int
    room_name: str
    livekit_token: str
    livekit_url: str


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
