from datetime import datetime

from pydantic import BaseModel


class CefrPointOut(BaseModel):
    session_id: int
    started_at: datetime
    level: str


class RecurringErrorOut(BaseModel):
    error_type: str
    count: int
    latest_correction: str


class ProgressOut(BaseModel):
    cefr_trend: list[CefrPointOut]
    recurring_errors: list[RecurringErrorOut]
