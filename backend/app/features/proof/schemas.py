from pydantic import BaseModel


class ProofOut(BaseModel):
    skill: str
    baseline_session_id: int
    latest_session_id: int
    baseline_started_at: str
    latest_started_at: str
    baseline_cefr: str
    latest_cefr: str
    # Factual, from debriefs — never an invented score.
    resolved: list[str]
    new_or_worse: list[str]
