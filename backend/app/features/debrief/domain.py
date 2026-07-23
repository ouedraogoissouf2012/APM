from dataclasses import dataclass, field

VALID_CEFR = {"A1", "A2", "B1", "B2", "C1", "C2"}


@dataclass(frozen=True)
class DebriefError:
    original: str
    correction: str
    rule: str
    error_type: str
    # Richer teaching content (defaults keep older debriefs valid):
    explanation: str = ""  # 2-3 sentences: WHY it was wrong, for the learner
    examples: list[str] = field(default_factory=list)  # correct example sentences
    alternatives: list[str] = field(default_factory=list)  # other ways to say it


@dataclass
class DebriefResult:
    cefr_estimate: str
    summary: str
    errors: list[DebriefError] = field(default_factory=list)
