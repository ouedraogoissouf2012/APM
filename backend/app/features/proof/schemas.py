from pydantic import BaseModel


class ProofOut(BaseModel):
    skill: str
    baseline_session_id: int
    latest_session_id: int
    baseline_started_at: str
    latest_started_at: str
    baseline_cefr: str
    latest_cefr: str
    # Learner-turn counts at each end, so the client can show the comparison's basis
    # (a shorter session isn't spun as progress — the deltas below are per-turn).
    baseline_turns: int
    latest_turns: int
    # Factual, from debriefs — never an invented score.
    resolved: list[str]  # made before, entirely gone now
    improved: list[str]  # still made, but less often per turn
    new_or_worse: list[str]  # appeared or more frequent per turn
