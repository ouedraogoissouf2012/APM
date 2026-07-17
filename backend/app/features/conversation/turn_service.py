"""Text-based conversation turn.

The mobile app does speech-to-text and text-to-speech ON DEVICE (free, no keys),
so the backend only needs the LLM turn: take the user's recognized text, reply
with the LLM (DeepSeek), and keep the transcript. No audio, no LiveKit.
"""

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
        session = await get_owned_session(self._sessions, session_id, user.id)
        if session.ended_at is not None:
            raise ConflictError("Session already ended")

        existing = await self._transcripts.get_by_session(session_id)
        turns: list[dict] = list(existing.turns) if existing is not None else []

        # Personalize from the learner's profile (interests + goal), if any.
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

        reply = await self._llm.complete(system_prompt, history)

        turns.append({"role": ROLE_USER, "content": text})
        turns.append({"role": ROLE_ASSISTANT, "content": reply})
        await self._transcripts.save(session_id, turns)
        return TurnResult(reply=reply, turns=turns)
