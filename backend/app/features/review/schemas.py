from datetime import datetime

from pydantic import BaseModel


class ReviewItemOut(BaseModel):
    error_type: str
    latest_correction: str
    stage: int
    clean_streak: int
    status: str
    next_review_at: datetime | None

    model_config = {"from_attributes": True}
