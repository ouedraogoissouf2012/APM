from dataclasses import dataclass

# Coarse per-level guidance (comprehensible input / i+1).
_LEVEL_GUIDANCE = {
    "A1": "Use very simple words and short present-tense sentences. Speak slowly.",
    "A2": "Use simple everyday vocabulary and short sentences. Avoid idioms.",
    "B1": "Use common vocabulary and a mix of tenses. Introduce occasional new words.",
    "B2": "Use natural vocabulary and varied structures. Challenge the learner slightly.",
    "C1": "Use rich, idiomatic English at near-native pace.",
    "C2": "Use fully native, nuanced English.",
}


@dataclass(frozen=True)
class PromptContext:
    cefr_level: str
    scenario_id: str | None
    interests: list[str]
    memory_summary: str


def build_system_prompt(ctx: PromptContext) -> str:
    level = ctx.cefr_level.upper()
    guidance = _LEVEL_GUIDANCE.get(level, _LEVEL_GUIDANCE["B1"])

    parts = [
        "You are a warm, patient English-speaking partner for a language learner.",
        f"The learner's CEFR level is {level}. {guidance}",
        "Keep your turns short so the learner does most of the talking, and ask an open "
        "question at the end of most turns to keep the conversation going.",
        "Do NOT correct the learner's mistakes during the conversation; stay in the flow. "
        "Mistakes are reviewed afterwards in a separate debrief.",
        "Never switch to the learner's native language unless they are completely stuck.",
    ]
    if ctx.scenario_id:
        parts.append(f"Play your role in this scenario: {ctx.scenario_id}.")
    if ctx.interests:
        parts.append("The learner is interested in: " + ", ".join(ctx.interests) + ".")
    if ctx.memory_summary:
        parts.append("Context from previous conversations: " + ctx.memory_summary)
    return "\n".join(parts)
