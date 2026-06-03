import pytest

from app.features.conversation.messages import Message
from app.features.conversation.pipeline import ConversationPipeline
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


@pytest.mark.asyncio
async def test_pipeline_runs_a_turn_and_records_transcript():
    pipeline = ConversationPipeline(
        stt=FakeStt(transcripts=["I go to school yesterday"]),
        llm=FakeLlm(),
        tts=FakeTts(),
        system_prompt="system",
    )
    audio_out = await pipeline.handle_user_audio(b"\x00")

    assert isinstance(audio_out, bytes)
    assert pipeline.transcript.to_dicts() == [
        {"role": "user", "content": "I go to school yesterday"},
        {"role": "assistant", "content": "You said: I go to school yesterday"},
    ]


@pytest.mark.asyncio
async def test_pipeline_passes_system_prompt_and_history_to_llm():
    captured = {}

    class RecordingLlm:
        async def complete(self, system_prompt, history):
            captured["system_prompt"] = system_prompt
            captured["history_len"] = len(history)
            return "ok"

    pipeline = ConversationPipeline(
        stt=FakeStt(transcripts=["hello"]),
        llm=RecordingLlm(),
        tts=FakeTts(),
        system_prompt="THE-PROMPT",
    )
    await pipeline.handle_user_audio(b"\x00")
    assert captured["system_prompt"] == "THE-PROMPT"
    assert captured["history_len"] == 1  # the user message, before the assistant reply
