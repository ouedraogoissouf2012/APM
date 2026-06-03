from app.features.conversation.messages import Transcript
from app.features.conversation.providers.interfaces import (
    LlmProvider,
    SttProvider,
    TtsProvider,
)


class ConversationPipeline:
    """Runs one conversational turn: audio -> STT -> LLM -> TTS -> audio.

    Records both sides into `transcript` for the later debrief.
    """

    def __init__(
        self,
        stt: SttProvider,
        llm: LlmProvider,
        tts: TtsProvider,
        system_prompt: str,
    ) -> None:
        self._stt = stt
        self._llm = llm
        self._tts = tts
        self._system_prompt = system_prompt
        self.transcript = Transcript()

    async def handle_user_audio(self, audio: bytes) -> bytes:
        user_text = await self._stt.transcribe(audio)
        self.transcript.add_user(user_text)
        reply = await self._llm.complete(self._system_prompt, list(self.transcript.messages))
        self.transcript.add_assistant(reply)
        return await self._tts.synthesize(reply)
