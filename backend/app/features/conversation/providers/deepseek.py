from typing import Any

from app.features.conversation.messages import Message


class DeepSeekLlmProvider:
    """LLM stage backed by DeepSeek's OpenAI-compatible API.

    The async client is injected so the provider is unit-testable without a key.
    Use `deepseek-chat` (V3) for low latency, not the slow reasoner model.
    """

    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self._model = model

    async def complete(self, system_prompt: str, history: list[Message]) -> str:
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        messages += [{"role": m.role, "content": m.content} for m in history]
        response = await self._client.chat.completions.create(model=self._model, messages=messages)
        return response.choices[0].message.content or ""


def build_deepseek_client(api_key: str, base_url: str) -> Any:
    """Construct the real DeepSeek (OpenAI-compatible) async client."""
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=api_key, base_url=base_url)
