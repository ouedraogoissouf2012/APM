"""Adaptive CEFR level progression.

The debrief produces a per-session CEFR *estimate*. To keep the conversation
difficulty adapting to the learner without oscillating, we move the learner's
stored level at most ONE CEFR step toward the latest estimate per session.
"""

CEFR_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]


def next_cefr_level(current: str, estimate: str) -> str:
    """Return the learner's next level: one step toward `estimate`, capped.

    Unknown `current` falls back to A1; unknown `estimate` leaves the level
    unchanged (defensive against a malformed LLM estimate).
    """
    if current not in CEFR_LEVELS:
        current = "A1"
    if estimate not in CEFR_LEVELS:
        return current
    cur = CEFR_LEVELS.index(current)
    est = CEFR_LEVELS.index(estimate)
    if est > cur:
        return CEFR_LEVELS[cur + 1]
    if est < cur:
        return CEFR_LEVELS[cur - 1]
    return current
