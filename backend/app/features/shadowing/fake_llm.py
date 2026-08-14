import json

from app.core.llm.messages import Message


class FakeShadowingLlm:
    """Returns valid (but generic) JSON for both the phrase generator and the
    coach, so the default `shadowing_engine=fake` works offline. It answers with
    a coaching payload if the prompt asks for coaching, otherwise a phrase.
    Set SHADOWING_ENGINE=deepseek for real, tailored output."""

    async def complete(self, system_prompt: str, history: list[Message]) -> str:
        if "coach" in system_prompt.lower():
            return json.dumps(
                {"coaching": "Demo coaching — set SHADOWING_ENGINE=deepseek for real tips."}
            )
        return json.dumps(
            {
                "text": "The ship is sinking.",
                "focus": "ship_sheep",
                "tip": "Keep the vowel short in 'ship' (demo — set SHADOWING_ENGINE=deepseek).",
            }
        )
