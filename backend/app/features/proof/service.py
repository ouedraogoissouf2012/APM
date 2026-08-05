"""Before/after proof of progress for a skill (#126).

The proof is the DIFFERENCE between the learner's first and latest session on the
same skill (keyed by scenario), computed from the debriefs already stored — never
an invented score. It reports which error types were resolved (and, honestly, any
that got worse), plus the CEFR estimates at each end. The audio A/B itself lives
on the device; this service only supplies the factual delta the screen shows.
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class SessionErrors:
    session_id: int
    started_at: str  # ISO
    cefr: str
    error_counts: dict[str, int]  # error_type -> count in that session


@dataclass
class ProofDelta:
    skill: str
    baseline_session_id: int
    latest_session_id: int
    baseline_started_at: str
    latest_started_at: str
    baseline_cefr: str
    latest_cefr: str
    # error types the learner made at baseline and no longer makes (count -> 0/less)
    resolved: list[str] = field(default_factory=list)
    # error types that appeared or increased since baseline (honest regressions)
    new_or_worse: list[str] = field(default_factory=list)


class ProofDataSource(Protocol):
    async def sessions_for_skill(self, user_id: int, skill: str) -> list[SessionErrors]:
        """Ended sessions for the skill that have a debrief, oldest first."""
        ...


class ProofService:
    def __init__(self, source: ProofDataSource) -> None:
        self._source = source

    async def proof(self, user_id: int, skill: str) -> ProofDelta | None:
        """The before/after delta, or None when there aren't yet two sessions on
        the skill to compare (the UI then shows a 'not enough yet' state)."""
        sessions = await self._source.sessions_for_skill(user_id, skill)
        if len(sessions) < 2:
            return None

        baseline = sessions[0]
        latest = sessions[-1]
        return ProofDelta(
            skill=skill,
            baseline_session_id=baseline.session_id,
            latest_session_id=latest.session_id,
            baseline_started_at=baseline.started_at,
            latest_started_at=latest.started_at,
            baseline_cefr=baseline.cefr,
            latest_cefr=latest.cefr,
            resolved=self._resolved(baseline.error_counts, latest.error_counts),
            new_or_worse=self._new_or_worse(baseline.error_counts, latest.error_counts),
        )

    @staticmethod
    def _resolved(baseline: dict[str, int], latest: dict[str, int]) -> list[str]:
        base, late = Counter(baseline), Counter(latest)
        # Present at baseline, strictly fewer (or none) now.
        return sorted(t for t, n in base.items() if n > 0 and late.get(t, 0) < n)

    @staticmethod
    def _new_or_worse(baseline: dict[str, int], latest: dict[str, int]) -> list[str]:
        base, late = Counter(baseline), Counter(latest)
        return sorted(t for t, n in late.items() if n > 0 and n > base.get(t, 0))
