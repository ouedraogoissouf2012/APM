from pydantic import BaseModel


class ProfileOut(BaseModel):
    interests: list[str]
    goal: str | None
    correction_intensity: str
    accent: str

    model_config = {"from_attributes": True}


class ProfileUpdate(BaseModel):
    interests: list[str] | None = None
    goal: str | None = None
    correction_intensity: str | None = None
    accent: str | None = None
