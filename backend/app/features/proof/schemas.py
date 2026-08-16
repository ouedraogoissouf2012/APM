from pydantic import BaseModel, Field


class ProofOut(BaseModel):
    skill: str
    # #443: not enough sessions is a 200 empty state, not a 404.
    insufficient_data: bool = False
    baseline_session_id: int | None = None
    latest_session_id: int | None = None
    baseline_started_at: str | None = None
    latest_started_at: str | None = None
    baseline_cefr: str | None = None
    latest_cefr: str | None = None
    # Learner-turn counts at each end, so the client can show the comparison's basis
    # (a shorter session isn't spun as progress — the deltas below are per-turn).
    baseline_turns: int = 0
    latest_turns: int = 0
    # Factual, from debriefs — never an invented score.
    resolved: list[str] = Field(default_factory=list)
    improved: list[str] = Field(default_factory=list)
    new_or_worse: list[str] = Field(default_factory=list)
