"""Text-based conversation turn.

The mobile app does speech-to-text and text-to-speech ON DEVICE (free, no keys),
so the backend only needs the LLM turn: take the user's recognized text, reply
with the LLM (DeepSeek), and keep the transcript. No audio, no LiveKit.
"""

import asyncio
import base64
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.domain.exceptions import ConflictError
from app.features.auth.models import User
from app.features.conversation.correction import TurnCorrection, TurnCorrector
from app.features.conversation.messages import ROLE_ASSISTANT, ROLE_USER, Message
from app.features.conversation.prompt import PromptContext, build_system_prompt
from app.features.conversation.providers.interfaces import LlmProvider, TtsProvider
from app.features.conversation.repository import TranscriptRepository
from app.features.profile.repository import ProfileRepository
from app.features.sessions.ownership import get_owned_session
from app.features.sessions.repository import SessionRepository


@dataclass
class TurnResult:
    reply: str
    turns: list[dict]


@dataclass(frozen=True)
class ReplyChunk:
    """One speakable sentence of the assistant's reply (text)."""

    text: str


@dataclass(frozen=True)
class AudioChunk:
    """Base64-encoded synthesized audio for one reply sentence, emitted right
    after its text so the client plays a real neural voice instead of the
    robotic on-device one. Only produced when a server-side TTS is configured."""

    audio_b64: str
    mime: str = "audio/mpeg"


@dataclass(frozen=True)
class CorrectionReady:
    """A grammar correction for the learner's utterance, emitted once, after
    the reply, so it never interrupts the spoken flow."""

    correction: TurnCorrection


# What `stream_turn` yields: per sentence a text chunk (+ optional audio), then
# at most one correction.
TurnStreamEvent = ReplyChunk | AudioChunk | CorrectionReady


class ConversationTurnService:
    def __init__(
        self,
        sessions: SessionRepository,
        transcripts: TranscriptRepository,
        profiles: ProfileRepository,
        llm: LlmProvider,
        corrector: TurnCorrector | None = None,
        tts: TtsProvider | None = None,
    ) -> None:
        self._sessions = sessions
        self._transcripts = transcripts
        self._profiles = profiles
        self._llm = llm
        self._corrector = corrector
        self._tts = tts

    async def take_turn(self, session_id: int, user: User, text: str) -> TurnResult:
        turns, system_prompt, history = await self._prepare(session_id, user, text)
        reply = await self._llm.complete(system_prompt, history)
        turns = await self._persist(session_id, turns, text, reply)
        return TurnResult(reply=reply, turns=turns)

    async def stream_turn(
        self, session_id: int, user: User, text: str
    ) -> AsyncIterator[TurnStreamEvent]:
        """Stream the reply sentence by sentence (text appears live), then speak
        it. The spoken audio is synthesized for the WHOLE reply as ONE clip
        (emitted after the text), not per sentence: playing many short clips
        back-to-back on the client cuts sentences off. A grammar correction for
        the learner's utterance is computed IN PARALLEL and emitted last, so the
        gold chip never breaks the flow."""
        turns, system_prompt, history = await self._prepare(session_id, user, text)
        correction_task: asyncio.Future[TurnCorrection | None] | None = None
        try:
            parts: list[str] = []
            async for sentence in self._llm.stream_complete(system_prompt, history):
                parts.append(sentence)
                yield ReplyChunk(sentence)
                # Start the correction only once the reply is already streaming,
                # so its concurrent LLM call cannot delay the reply's first token
                # (the latency the learner actually feels). It still overlaps the
                # rest of the reply + its spoken playback, so the chip is ready in
                # time.
                if correction_task is None and self._corrector is not None:
                    correction_task = asyncio.ensure_future(
                        self._corrector.correct(
                            text, user.cefr_level, user.native_language
                        )
                    )
            full_reply = " ".join(parts)
            await self._persist(session_id, turns, text, full_reply)
            # Speak the whole reply as one clean clip. TTS failure must not break
            # the turn (the text reply already succeeded).
            if self._tts is not None and full_reply:
                try:
                    audio = await self._tts.synthesize(full_reply)
                except Exception:
                    audio = b""
                if audio:
                    yield AudioChunk(base64.b64encode(audio).decode("ascii"))
            if correction_task is not None:
                correction = await correction_task
                if correction is not None:
                    yield CorrectionReady(correction)
        finally:
            # If the reply stream errored or the consumer stopped early, don't
            # leak the parallel correction task.
            if correction_task is not None and not correction_task.done():
                correction_task.cancel()

    async def _prepare(
        self, session_id: int, user: User, text: str
    ) -> tuple[list[dict], str, list[Message]]:
        """Validate ownership/state, load history, and build the system prompt
        from the learner's profile. Shared by take_turn and stream_turn."""
        session = await get_owned_session(self._sessions, session_id, user.id)
        if session.ended_at is not None:
            raise ConflictError("Session already ended")

        existing = await self._transcripts.get_by_session(session_id)
        turns: list[dict] = list(existing.turns) if existing is not None else []

        profile = await self._profiles.get_by_user_id(user.id)
        interests = list(profile.interests) if profile is not None else []
        goal = profile.goal if profile is not None and profile.goal else ""
        memory_summary = profile.memory_summary if profile is not None else ""

        system_prompt = build_system_prompt(
            PromptContext(
                cefr_level=user.cefr_level,
                scenario_id=session.scenario_id,
                interests=interests,
                memory_summary=memory_summary,
                goal=goal,
            )
        )
        history = [Message(role=t["role"], content=t["content"]) for t in turns]
        history.append(Message(role=ROLE_USER, content=text))
        return turns, system_prompt, history

    async def _persist(
        self, session_id: int, turns: list[dict], text: str, reply: str
    ) -> list[dict]:
        turns = [
            *turns,
            {"role": ROLE_USER, "content": text},
            {"role": ROLE_ASSISTANT, "content": reply},
        ]
        await self._transcripts.save(session_id, turns)
        return turns
