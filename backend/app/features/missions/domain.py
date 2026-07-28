"""Pure domain types for missions — no I/O, no framework.

A "mission" turns a real situation the learner is preparing for (a job offer, a
CV, a pitch, an upcoming call) into a tailored spoken simulation: who they will
talk to, what the goal is, the questions likely to come up, and the system
prompt that drives the conversation LLM.
"""

from dataclasses import dataclass, field
from typing import Literal, get_args

# The kind of raw material the learner provides. `freeform` is a plain
# description of the situation; the others hint at how to read the content.
SourceType = Literal["offer", "cv", "pitch", "topic", "freeform"]

SOURCE_TYPES: tuple[SourceType, ...] = get_args(SourceType)


@dataclass(frozen=True)
class MissionBrief:
    """A compiled simulation. `system_prompt` is computed server-side and is the
    only field the conversation LLM is driven by — it is never accepted from the
    client (an attacker-controlled prompt would hijack the tutor)."""

    persona: str
    goal: str
    likely_questions: list[str] = field(default_factory=list)
    system_prompt: str = ""
