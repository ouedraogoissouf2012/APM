import pytest

from app.domain.exceptions import LlmProviderError
from app.features.conversation.messages import Message
from app.features.conversation.providers.deepseek import DeepSeekLlmProvider


class _StubMessage:
    def __init__(self, content):
        self.content = content


class _StubChoice:
    def __init__(self, content):
        self.message = _StubMessage(content)


class _StubResponse:
    def __init__(self, content):
        self.choices = [_StubChoice(content)]


class _StubCompletions:
    def __init__(self, recorder, content="Bonjour back"):
        self._recorder = recorder
        self._content = content

    async def create(self, *, model, messages):
        self._recorder["model"] = model
        self._recorder["messages"] = messages
        return _StubResponse(self._content)


class _StubChat:
    def __init__(self, recorder, content="Bonjour back"):
        self.completions = _StubCompletions(recorder, content)


class _StubClient:
    def __init__(self, recorder, content="Bonjour back"):
        self.chat = _StubChat(recorder, content)


class _FailingCompletions:
    async def create(self, *, model, messages):
        raise RuntimeError("network down")


class _FailingChat:
    completions = _FailingCompletions()


class _FailingClient:
    chat = _FailingChat()


@pytest.mark.asyncio
async def test_deepseek_builds_messages_and_parses_reply():
    recorder: dict = {}
    provider = DeepSeekLlmProvider(client=_StubClient(recorder), model="deepseek-chat")

    reply = await provider.complete("SYSTEM", [Message(role="user", content="hello")])

    assert reply == "Bonjour back"
    assert recorder["model"] == "deepseek-chat"
    assert recorder["messages"][0] == {"role": "system", "content": "SYSTEM"}
    assert recorder["messages"][1] == {"role": "user", "content": "hello"}


@pytest.mark.asyncio
async def test_deepseek_returns_empty_string_when_content_is_none():
    provider = DeepSeekLlmProvider(client=_StubClient({}, content=None), model="deepseek-chat")
    assert await provider.complete("s", [Message(role="user", content="x")]) == ""


@pytest.mark.asyncio
async def test_deepseek_wraps_provider_failures_in_domain_error():
    provider = DeepSeekLlmProvider(client=_FailingClient(), model="deepseek-chat")
    with pytest.raises(LlmProviderError):
        await provider.complete("s", [Message(role="user", content="x")])
