import pytest

from app.features.conversation.messages import Message
from app.features.conversation.providers.fakes import FakeLlm, FakeStt, FakeTts


@pytest.mark.asyncio
async def test_fake_stt_returns_scripted_text():
    stt = FakeStt(transcripts=["hello there"])
    assert await stt.transcribe(b"\x00\x01") == "hello there"


@pytest.mark.asyncio
async def test_fake_llm_echoes_last_user_message():
    llm = FakeLlm()
    reply = await llm.complete("system", [Message(role="user", content="ping")])
    assert "ping" in reply


@pytest.mark.asyncio
async def test_fake_tts_returns_bytes_for_text():
    tts = FakeTts()
    audio = await tts.synthesize("hi")
    assert isinstance(audio, bytes)
    assert audio == b"hi"
