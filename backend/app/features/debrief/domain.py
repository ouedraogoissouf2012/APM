from dataclasses import dataclass, field

VALID_CEFR = {"A1", "A2", "B1", "B2", "C1", "C2"}


@dataclass(frozen=True)
class DebriefError:
    original: str
    correction: str
    rule: str
    error_type: str


@dataclass
class DebriefResult:
    cefr_estimate: str
    summary: str
    errors: list[DebriefError] = field(default_factory=list)
