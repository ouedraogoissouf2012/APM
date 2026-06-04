from pydantic import BaseModel


class DebriefErrorOut(BaseModel):
    original: str
    correction: str
    rule: str
    error_type: str


class DebriefOut(BaseModel):
    session_id: int
    cefr_estimate: str
    summary: str
    errors: list[DebriefErrorOut]

    model_config = {"from_attributes": True}
