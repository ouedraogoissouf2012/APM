from pydantic import BaseModel


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
    baseline_turns: int
    latest_turns: int
    # Factual, from debriefs — never an invented score.
    resolved: list[str]  # made before, entirely gone now
    improved: list[str]  # still made, but less often per turn
    new_or_worse: list[str]  # appeared or more frequent per turn
