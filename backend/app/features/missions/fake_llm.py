import json

from app.features.conversation.messages import Message


class FakeMissionLlm:
    """Returns a valid (but generic) mission brief JSON so the default
    `mission_engine=fake` yields a usable simulation locally instead of failing to
    parse. No network. Set MISSION_ENGINE=deepseek for a real, tailored brief."""

    async def complete(self, system_prompt: str, history: list[Message]) -> str:
        return json.dumps(
            {
                "persona": "A friendly interviewer (demo mission — set "
                "MISSION_ENGINE=deepseek for a real simulation).",
                "goal": "Practise introducing yourself clearly and confidently.",
                "likely_questions": [
                    "Tell me about yourself.",
                    "Why are you interested in this?",
                    "What is one of your strengths?",
                ],
            }
        )
