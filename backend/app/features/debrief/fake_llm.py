import json

from app.features.conversation.messages import Message


class FakeDebriefLlm:
    """Returns a valid (but generic) debrief JSON so the default `debrief_engine=fake`
    yields a usable result locally instead of failing to parse. No network."""

    async def complete(self, system_prompt: str, history: list[Message]) -> str:
        return json.dumps(
            {
                "cefr_estimate": "B1",
                "summary": "Demo debrief (fake engine). Set DEBRIEF_ENGINE=deepseek for real.",
                "errors": [],
            }
        )
