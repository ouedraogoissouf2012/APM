"""Text-based conversation turn.

The mobile app does speech-to-text and text-to-speech ON DEVICE (free, no keys),
so the backend only needs the LLM turn: take the user's recognized text, reply
with the LLM (DeepSeek), and keep the transcript. No audio, no LiveKit.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.domain.exceptions import ConflictError
from app.features.auth.models import User
from app.features.conversation.messages import ROLE_ASSISTANT, ROLE_USER, Message
from app.features.conversation.prompt import PromptContext, build_system_prompt
from app.features.conversation.providers.interfaces import LlmProvider
from app.features.conversation.repository import TranscriptRepository
from app.features.profile.repository import ProfileRepository
from app.features.sessions.ownership import get_owned_session
from app.features.sessions.repository import SessionRepository


@dataclass
class TurnResult:
    reply: str
    turns: list[dict]


@dataclass
class PreparedTurn:
    """A validated turn ready to stream and then persist. Produced by
    ConversationTurnService.prepare_turn BEFORE any streaming response starts,
    so ownership/state failures become proper HTTP errors, not broken streams."""

    session_id: int
    turns: list[dict]
    text: str
    system_prompt: str
    history: list[Message]


class ConversationTurnService:
    def __init__(
        self,
        sessions: SessionRepository,
        transcripts: TranscriptRepository,
        profiles: ProfileRepository,
        llm: LlmProvider,
    ) -> None:
        self._sessions = sessions
        self._transcripts = transcripts
        self._profiles = profiles
        self._llm = llm

    async def take_turn(self, session_id: int, user: User, text: str) -> TurnResult:
        turns, system_prompt, history = await self._prepare(session_id, user, text)
        reply = await self._llm.complete(system_prompt, history)
        turns = await self._persist(session_id, turns, text, reply)
        return TurnResult(reply=reply, turns=turns)

    async def stream_turn(self, session_id: int, user: User, text: str) -> AsyncIterator[str]:
        """Validate, then stream the reply sentence by sentence and persist it.
        A single entry point for callers that don't need to separate validation
        from streaming; the streaming route splits the two (see prepare_turn)."""
        prepared = await self.prepare_turn(session_id, user, text)
        async for sentence in self.stream_prepared(prepared):
            yield sentence

    async def prepare_turn(self, session_id: int, user: User, text: str) -> PreparedTurn:
        """Validate ownership/state and build the prompt+history for a turn.
        Call (and await) this BEFORE returning a streaming response, so a
        not-owned or ended session surfaces as a proper 404/409 instead of a
        broken error mid-stream — once StreamingResponse starts, the 200 status
        is already committed and the real status can no longer be sent."""
        turns, system_prompt, history = await self._prepare(session_id, user, text)
        return PreparedTurn(
            session_id=session_id,
            turns=turns,
            text=text,
            system_prompt=system_prompt,
            history=history,
        )

    async def stream_prepared(self, prepared: PreparedTurn) -> AsyncIterator[str]:
        """Stream the reply for an already-validated turn, sentence by sentence,
        persisting whatever was produced even if the provider fails mid-stream."""
        parts: list[str] = []
        try:
            async for sentence in self._llm.stream_complete(
                prepared.system_prompt, prepared.history
            ):
                parts.append(sentence)
                yield sentence
        finally:
            # Persist whatever was actually produced. A mid-stream provider
            # failure — or an early client disconnect — must not silently drop a
            # reply the learner already heard: that would desync the transcript
            # the next turn and the debrief read back. Nothing produced yet means
            # nothing to persist (consistent with take_turn on a failed reply).
            if parts:
                await self._persist(
                    prepared.session_id,
                    prepared.turns,
                    prepared.text,
                    " ".join(parts),
                )

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
