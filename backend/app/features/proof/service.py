"""Before/after proof of progress for a skill (#126).

The proof is the DIFFERENCE between the learner's first and latest session on the
same skill (keyed by scenario), computed from the debriefs already stored — never
an invented score. Error types are classified honestly: `resolved` only when a type
is ENTIRELY gone (not merely reduced), `improved` when it is less frequent per turn
but still made, and `new_or_worse` when it appeared or got more frequent. All
comparisons are per learner-turn, so a shorter latest session cannot masquerade as
progress. The audio A/B itself lives on the device; this service only supplies the
factual delta the screen shows.
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
    turn_count: int = 0  # learner turns in the session, for length-normalised rates


@dataclass
class ProofDelta:
    skill: str
    baseline_session_id: int
    latest_session_id: int
    baseline_started_at: str
    latest_started_at: str
    baseline_cefr: str
    latest_cefr: str
    # Learner-turn counts at each end, so a shorter session can't masquerade as
    # progress: the comparison below is by per-turn RATE, and these expose the base.
    baseline_turns: int
    latest_turns: int
    # error types made at baseline and ENTIRELY GONE now (count -> 0)
    resolved: list[str] = field(default_factory=list)
    # error types still made but LESS FREQUENT now (per-turn rate dropped, not zero)
    improved: list[str] = field(default_factory=list)
    # error types that appeared or got MORE FREQUENT since baseline (honest regressions)
    new_or_worse: list[str] = field(default_factory=list)


class ProofDataSource(Protocol):
    async def sessions_for_skill(self, user_id: int, skill: str) -> list[SessionErrors]:
        """The baseline (earliest) and latest ended sessions for the skill that
        have a debrief, oldest first: `[]` when none match, one element when
        only a single session does, two when there's a before/after to compare.
        """
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
            baseline_turns=baseline.turn_count,
            latest_turns=latest.turn_count,
            resolved=self._resolved(baseline, latest),
            improved=self._improved(baseline, latest),
            new_or_worse=self._new_or_worse(baseline, latest),
        )

    @staticmethod
    def _rate(count: int, turns: int) -> float:
        # Errors per learner turn. Falls back to the raw count when the turn count
        # is unknown (0), so an un-instrumented session still compares sanely.
        return count / turns if turns > 0 else float(count)

    @staticmethod
    def _resolved(baseline: SessionErrors, latest: SessionErrors) -> list[str]:
        # Made at baseline and ENTIRELY gone now — not merely reduced. A partial
        # reduction (3 -> 1) is 'improved', not 'resolved': the learner still makes it.
        late = Counter(latest.error_counts)
        return sorted(t for t, n in baseline.error_counts.items() if n > 0 and late.get(t, 0) == 0)

    @classmethod
    def _improved(cls, baseline: SessionErrors, latest: SessionErrors) -> list[str]:
        # Still present, but at a lower per-turn rate — honest 'in progress'.
        out = []
        for t, n in baseline.error_counts.items():
            late_n = latest.error_counts.get(t, 0)
            if (
                n > 0
                and late_n > 0
                and cls._rate(late_n, latest.turn_count) < cls._rate(n, baseline.turn_count)
            ):
                out.append(t)
        return sorted(out)

    @classmethod
    def _new_or_worse(cls, baseline: SessionErrors, latest: SessionErrors) -> list[str]:
        # Appeared, or got MORE frequent per turn — normalised so a short session
        # can't hide a regression behind a smaller raw count.
        out = []
        for t, late_n in latest.error_counts.items():
            base_n = baseline.error_counts.get(t, 0)
            if late_n > 0 and cls._rate(late_n, latest.turn_count) > cls._rate(
                base_n, baseline.turn_count
            ):
                out.append(t)
        return sorted(out)
