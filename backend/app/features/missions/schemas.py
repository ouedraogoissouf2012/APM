from pydantic import BaseModel, Field

from app.features.missions.domain import SourceType


class MissionIn(BaseModel):
    """Raw material the learner provides. `content` is bounded so a huge paste
    cannot blow up token cost; `source_type` is Literal-validated (a bad value is
    rejected with 422 before any LLM call)."""

    source_type: SourceType
    content: str = Field(min_length=1, max_length=6000)


class MissionOut(BaseModel):
    """The compiled simulation. `system_prompt` is deliberately NOT exposed — it
    is a server-side internal used to drive the conversation, never round-tripped
    through the client."""

    id: int
    source_type: str
    persona: str
    goal: str
    likely_questions: list[str]

    model_config = {"from_attributes": True}
