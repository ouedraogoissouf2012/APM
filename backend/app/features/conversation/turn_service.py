"""Conversation turn: LLM reply, optional server-side voice, live correction.

The turn is driven by text — the client sends the learner's recognized words and
the backend replies with the LLM (DeepSeek), keeping the transcript. Speech I/O
can run either on-device (free, no keys) OR server-side: when a `TtsProvider` is
configured the reply is synthesized to neural audio here (see `AudioChunk`), and
a separate STT endpoint transcribes recorded audio. A grammar correction of the
learner's utterance is computed in parallel and streamed last. No LiveKit.
"""

import asyncio
import base64
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime

from app.core.llm.interfaces import LlmProvider, TtsProvider
from app.core.llm.messages import ROLE_ASSISTANT, ROLE_USER, Message
from app.domain.exceptions import ConflictError
from app.features.auth.models import User
from app.features.conversation.correction import TurnCorrection, TurnCorrector
from app.features.conversation.prompt import PromptContext, build_system_prompt
from app.features.conversation.repository import TranscriptRepository
from app.features.missions.repository import MissionRepository
from app.features.profile.repository import ProfileRepository
from app.features.sessions.models import ConversationSession
from app.features.sessions.ownership import get_owned_session
from app.features.sessions.repository import SessionRepository
from app.features.sessions.service import clamp_practiced_at


@dataclass(frozen=True)
class TurnPersistence:
    """A fresh, short-lived unit of work for the TERMINAL write of a turn (#399).

    The hot conversation paths (take_turn, stream_prepared) hold no DB connection
    across the multi-second LLM/TTS I/O: the request's connection is released at the
    I/O boundary, and the transcript save + quota meter run afterwards against a
    FRESH connection opened here. Bundles the transcript repository and the meter so
    both write on the SAME fresh session (one connection, not two)."""

    transcripts: TranscriptRepository
    meter: Callable[[int, int], Awaitable[None]] | None


# A factory that opens a fresh, short-lived persistence scope for the terminal
# write. Injected (DIP) so the service never touches an AsyncSession directly and
# stays unit-testable with an in-memory fake. None => reuse the request-scoped
# repositories passed to the constructor (the pre-#399 behaviour, kept for callers
# — and unit tests — that don't need connection release).
PersistenceScopeFactory = Callable[[], AbstractAsyncContextManager[TurnPersistence]]

# Called once per turn at the boundary between the DB reads (prepare) and the
# external I/O (LLM/TTS), to RELEASE the request's DB connection back to the pool
# so it isn't held idle for seconds (#399). Injected; None => no-op (the request
# connection is held for the whole request, the pre-#399 behaviour).
IoBoundaryHook = Callable[[], Awaitable[None]]


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
    """Base64-encoded synthesized audio for ONE reply sentence, emitted right
    after that sentence's text so the client can start the neural voice while the
    rest of the reply is still being written. The client plays the per-sentence
    clips sequentially (a background queue) so they never cut each other off. Only
    produced when a server-side TTS is configured."""

    audio_b64: str
    mime: str = "audio/mpeg"


@dataclass(frozen=True)
class CorrectionReady:
    """A grammar correction for the learner's utterance, emitted once, after
    the reply, so it never interrupts the spoken flow."""

    correction: TurnCorrection


# What `stream_turn` yields: a text chunk per sentence, then (optionally) one
# audio clip for the whole reply, then at most one correction.
TurnStreamEvent = ReplyChunk | AudioChunk | CorrectionReady


@dataclass
class PreparedTurn:
    """A validated turn, ready to stream and persist. Built by
    ConversationTurnService.prepare_turn BEFORE any streaming response begins, so
    ownership/state failures surface as a proper 404/409 instead of a committed
    200 stream that then emits a generic error."""

    session_id: int
    user: User
    text: str
    turns: list[dict]
    system_prompt: str
    history: list[Message]
    intensity: str


class ConversationTurnService:
    def __init__(
        self,
        sessions: SessionRepository,
        transcripts: TranscriptRepository,
        profiles: ProfileRepository,
        llm: LlmProvider,
        corrector: TurnCorrector | None = None,
        tts: TtsProvider | None = None,
        missions: MissionRepository | None = None,
        meter: Callable[[int, int], Awaitable[None]] | None = None,
        history_max_messages: int = 20,
        transcript_max_messages: int = 200,
        io_boundary: IoBoundaryHook | None = None,
        persistence: PersistenceScopeFactory | None = None,
    ) -> None:
        self._sessions = sessions
        self._transcripts = transcripts
        self._profiles = profiles
        self._llm = llm
        self._corrector = corrector
        self._tts = tts
        self._missions = missions
        # Sliding window of transcript messages replayed to the LLM per turn (#224);
        # 0 = unlimited. The PERSISTED transcript is separately bounded by
        # transcript_max_messages below — this window is a strict subset of it.
        self._history_max_messages = history_max_messages
        # Hard cap on the PERSISTED transcript itself (#364); 0 = unlimited. Without
        # this, a long-running session (unbounded on a paid tier, which has no
        # per-session quota) grows the transcript's JSONB column forever — every
        # turn re-reads and rewrites the WHOLE column, so the cost of a single turn
        # (and the write-amplified WAL it generates) grows with the session's
        # entire history instead of staying constant. Once the cap is hit, the
        # oldest messages age out (sliding window, like history_max_messages) so a
        # long session degrades gracefully (older debrief/proof context is lost)
        # rather than growing the DB row and every turn's cost without bound.
        self._transcript_max_messages = transcript_max_messages
        # Called once per turn to meter the quota per turn (#119). Injected (DIP)
        # so this service stays decoupled from the session/quota logic. Best-effort:
        # a metering failure must never break a turn. Used only when no fresh
        # persistence scope is injected (see _persist); the scope carries its own.
        self._meter = meter
        # #399: release the request's DB connection at the LLM/TTS boundary, then
        # persist on a FRESH short-lived connection — so the pool connection isn't
        # held idle across seconds of external I/O. Both are optional: when absent,
        # reads and the terminal write share the request connection (pre-#399).
        self._io_boundary = io_boundary
        self._persistence = persistence

    async def take_turn(
        self,
        session_id: int,
        user: User,
        text: str,
        *,
        practiced_at: datetime | None = None,
    ) -> TurnResult:
        turns, system_prompt, history, _intensity = await self._prepare(session_id, user, text)
        # #399: hand the request's DB connection back to the pool before the seconds
        # of LLM I/O below, then persist on a fresh one. All reads are done.
        await self._release_connection_for_io()
        reply = await self._llm.complete(system_prompt, history)
        async with self._open_persistence() as scope:
            turns = await self._persist(
                scope, session_id, user, turns, text, reply, practiced_at=practiced_at
            )
        return TurnResult(reply=reply, turns=turns)

    async def stream_turn(
        self, session_id: int, user: User, text: str
    ) -> AsyncIterator[TurnStreamEvent]:
        """Validate, then stream + persist. A single entry point for callers that
        don't need to separate validation from streaming; the streaming route
        splits the two so ownership/state errors get a proper HTTP status (see
        prepare_turn and stream_prepared)."""
        prepared = await self.prepare_turn(session_id, user, text)
        async for event in self.stream_prepared(prepared):
            yield event

    async def prepare_turn(self, session_id: int, user: User, text: str) -> PreparedTurn:
        """Validate ownership/state and build the prompt+history for a turn. Call
        (and await) this BEFORE returning a StreamingResponse: a not-owned or ended
        session then raises to the exception handlers (404/409). Once the stream
        starts the 200 is committed and the real status can no longer be sent — the
        failure would only surface as a generic error event."""
        turns, system_prompt, history, intensity = await self._prepare(session_id, user, text)
        return PreparedTurn(
            session_id=session_id,
            user=user,
            text=text,
            turns=turns,
            system_prompt=system_prompt,
            history=history,
            intensity=intensity,
        )

    async def stream_prepared(
        self,
        prepared: PreparedTurn,
        on_persisted: Callable[[str], Awaitable[None]] | None = None,
    ) -> AsyncIterator[TurnStreamEvent]:
        """Stream the reply for an already-validated turn sentence by sentence AND
        speak each sentence as it is produced: the audio for sentence N is
        synthesized while the LLM is still writing sentence N+1, so the voice starts
        after the first sentence (~1-2 s) instead of after the whole reply plus its
        synthesis (~5 s). The client plays the clips sequentially (await playClip),
        so per-sentence clips never cut each other off. A grammar correction for the
        learner's utterance is computed IN PARALLEL and emitted last, so the gold
        chip never breaks the flow.

        `on_persisted(reply)` is awaited RIGHT AFTER the turn is persisted + metered
        (both the full-reply and the partial-on-error paths), BEFORE any further SSE
        frame (correction/done) is yielded. The streaming route uses it to mark the
        idempotency key completed atomically with the side effect (#261): a client
        disconnect on a later frame then can't leave the turn persisted+charged yet
        the key un-completed (which a retry would re-persist and double-charge)."""
        session_id, user, text = prepared.session_id, prepared.user, prepared.text
        turns, system_prompt, history = prepared.turns, prepared.system_prompt, prepared.history
        intensity = prepared.intensity
        correction_task: asyncio.Future[TurnCorrection | None] | None = None
        # Synthesis of the previous sentence, running while the next one is being
        # generated. Awaited just before its audio is emitted, so clips stay ordered
        # yet overlap generation (the latency win).
        pending_audio: asyncio.Future[bytes] | None = None
        parts: list[str] = []
        # #399: the reads (prepare_turn) are done; release the request's DB
        # connection before the seconds of streamed LLM + per-sentence TTS below.
        # The terminal persist re-opens a fresh, short-lived one (see _persist).
        await self._release_connection_for_io()
        try:
            try:
                async for sentence in self._llm.stream_complete(system_prompt, history):
                    parts.append(sentence)
                    yield ReplyChunk(sentence)
                    # Emit the previous sentence's finished audio before kicking off the
                    # next, keeping clips in order.
                    async for event in self._drain_audio(pending_audio):
                        yield event
                    pending_audio = self._start_synthesis(sentence)
                    # Start the correction only once the reply is already streaming,
                    # so its concurrent LLM call cannot delay the reply's first token
                    # (the latency the learner actually feels).
                    if correction_task is None and self._corrector is not None:
                        correction_task = asyncio.ensure_future(
                            self._corrector.correct(
                                text, user.cefr_level, user.native_language, intensity
                            )
                        )
                # Emit the last sentence's audio.
                async for event in self._drain_audio(pending_audio):
                    yield event
                pending_audio = None
            except Exception:
                # The reply stream failed partway through. Persist what the learner
                # already heard so the exchange isn't silently dropped — a lost
                # partial reply would desync the next turn's history and the debrief.
                # Then re-raise so the router emits an `error` event. A clean client
                # disconnect arrives as CancelledError/GeneratorExit (not Exception)
                # and is intentionally NOT persisted here: a DB write during request
                # teardown is unsafe, and the normal path already saved on success.
                if parts:
                    partial = " ".join(parts)
                    async with self._open_persistence() as scope:
                        await self._persist(scope, session_id, user, turns, text, partial)
                    # The partial WAS persisted + metered — finalise the idempotency
                    # key on it so a retry replays the partial instead of re-charging.
                    if on_persisted is not None:
                        await on_persisted(partial)
                raise
            full_reply = " ".join(parts)
            try:
                async with self._open_persistence() as scope:
                    await self._persist(scope, session_id, user, turns, text, full_reply)
            except Exception:
                # The full reply was ALREADY delivered to the client — every
                # ReplyChunk (and its audio) was yielded above. A persist failure
                # NOW is not a turn error: re-raising would make the router emit an
                # `error` frame AFTER the learner already has the complete reply,
                # which is both misleading and still unsaved. Log the transcript
                # desync and let the stream end normally with `done` (#238). Do NOT
                # call on_persisted: nothing committed, so the idempotency key (#261)
                # stays un-completed and self-heals via the stale-reclaim window (a
                # retry re-runs after ~120s) rather than caching a phantom reply.
                logging.getLogger(__name__).exception(
                    "Turn reply fully delivered but transcript persist failed (session %s)",
                    session_id,
                )
            else:
                # Finalise idempotency ONLY when the turn actually persisted, so a
                # retry replays a COMMITTED turn (never an unsaved one). Done BEFORE
                # the correction/done frames so a disconnect on those can't desync the
                # committed turn from its key (#261).
                if on_persisted is not None:
                    await on_persisted(full_reply)
            if correction_task is not None:
                correction = await correction_task
                if correction is not None:
                    yield CorrectionReady(correction)
        finally:
            # If the reply stream errored or the consumer stopped early, don't
            # leak the parallel correction/synthesis tasks.
            if correction_task is not None and not correction_task.done():
                correction_task.cancel()
            if pending_audio is not None and not pending_audio.done():
                pending_audio.cancel()

    def _start_synthesis(self, sentence: str) -> asyncio.Future[bytes] | None:
        """Kick off TTS for one sentence in the background (or None if no server
        TTS). Runs while the next sentence is generated — that overlap is the win."""
        if self._tts is None:
            return None
        return asyncio.ensure_future(self._synthesize_quietly(sentence))

    async def _synthesize_quietly(self, sentence: str) -> bytes:
        """Synthesize one sentence; a TTS failure yields empty bytes rather than
        breaking the turn (the text reply already succeeded)."""
        assert self._tts is not None
        try:
            return await self._tts.synthesize(sentence)
        except Exception:
            # Empty audio keeps the turn flowing — the text reply already succeeded
            # (#236: but log it — a silent TTS gap otherwise leaves no server trace
            # of why the learner heard nothing for that sentence).
            logging.getLogger(__name__).warning("TTS synthesis failed", exc_info=True)
            return b""

    async def _drain_audio(
        self, pending: asyncio.Future[bytes] | None
    ) -> AsyncIterator[AudioChunk]:
        """Await a pending synthesis and yield its clip (skipping empty audio)."""
        if pending is None:
            return
        audio = await pending
        if audio:
            yield AudioChunk(base64.b64encode(audio).decode("ascii"))

    async def _prepare(
        self, session_id: int, user: User, text: str
    ) -> tuple[list[dict], str, list[Message], str]:
        """Validate ownership/state, load history, and build the system prompt from
        the learner's profile. Also surfaces the learner's correction_intensity so
        the corrector honours it (#114). Shared by take_turn and stream_turn."""
        session = await get_owned_session(self._sessions, session_id, user.id)
        if session.ended_at is not None:
            raise ConflictError("Session already ended")

        existing = await self._transcripts.get_by_session(session_id)
        turns: list[dict] = list(existing.turns) if existing is not None else []

        system_prompt, intensity = await self._prompt_and_intensity_for(session, user)
        # Only the last N messages go to the LLM (#224): replaying the WHOLE transcript
        # every turn makes cost + latency grow without bound in a long conversation.
        # `turns` (the persisted transcript, itself bounded by transcript_max_messages
        # — see _persist) is untouched here — it is still what the end-of-session
        # debrief analyses; the profile memory_summary in the system prompt carries
        # the older context the window (and, past the cap, the transcript itself) drops.
        window = turns[-self._history_max_messages :] if self._history_max_messages > 0 else turns
        history = [Message(role=t["role"], content=t["content"]) for t in window]
        history.append(Message(role=ROLE_USER, content=text))
        return turns, system_prompt, history, intensity

    async def _prompt_and_intensity_for(
        self, session: ConversationSession, user: User
    ) -> tuple[str, str]:
        """The system prompt plus the learner's correction intensity, from a single
        profile load. A mission session is driven by the mission's stored,
        server-computed system prompt (persona role-play); any other session uses
        the profile-based prompt. Falling back to the profile prompt if the mission
        vanished keeps a turn from breaking mid-conversation."""
        profile = await self._profiles.get_by_user_id(user.id)
        intensity = profile.correction_intensity if profile is not None else "gentle"

        if session.mission_id is not None and self._missions is not None:
            mission = await self._missions.get_owned(session.mission_id, user.id)
            if mission is not None and mission.system_prompt:
                return mission.system_prompt, intensity

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
        return system_prompt, intensity

    def _open_persistence(self) -> AbstractAsyncContextManager["TurnPersistence"]:
        """The unit of work for the terminal write. A fresh, short-lived scope (its
        own DB connection) when one is injected (#399); otherwise the request-scoped
        repositories the constructor was given — kept for callers and unit tests that
        don't need connection release. Either way the caller writes inside `async with`."""
        if self._persistence is not None:
            return self._persistence()
        return _null_persistence(TurnPersistence(self._transcripts, self._meter))

    async def _release_connection_for_io(self) -> None:
        """Release the request's DB connection back to the pool before external I/O
        (#399). No-op when no boundary hook is injected (the connection is then held
        for the whole request, as before)."""
        if self._io_boundary is not None:
            await self._io_boundary()

    async def _persist(
        self,
        scope: "TurnPersistence",
        session_id: int,
        user: User,
        turns: list[dict],
        text: str,
        reply: str,
        practiced_at: datetime | None = None,
    ) -> list[dict]:
        turns = [
            *turns,
            {"role": ROLE_USER, "content": text},
            {"role": ROLE_ASSISTANT, "content": reply},
        ]
        # Bound the PERSISTED transcript (#364): this exchange is always kept even
        # if `turns` was already at the cap; the oldest messages age out instead.
        if self._transcript_max_messages > 0 and len(turns) > self._transcript_max_messages:
            turns = turns[-self._transcript_max_messages :]
        # #399: write on the fresh persistence scope (own short-lived connection),
        # not the request repo whose connection was handed back at the I/O boundary.
        # #438: flush the transcript, then let the meter commit both on the
        # same fresh session. If the meter is missing or blows up, still commit
        # the transcript so the turn is not lost.
        await scope.transcripts.save(session_id, turns, commit=False)
        if scope.meter is not None:
            try:
                now = clamp_practiced_at(practiced_at)
                try:
                    await scope.meter(session_id, user.id, now=now)  # type: ignore[call-arg]
                except TypeError:
                    await scope.meter(session_id, user.id)
            except Exception:
                logging.getLogger(__name__).warning(
                    "Per-turn quota metering failed for session %s", session_id, exc_info=True
                )
                await scope.transcripts.commit()
        else:
            await scope.transcripts.commit()
        return turns


@contextlib.asynccontextmanager
async def _null_persistence(scope: TurnPersistence) -> AsyncIterator[TurnPersistence]:
    """Wrap already-constructed request-scoped repositories as a persistence scope
    with no setup/teardown — so _persist has a single, uniform `async with` path
    whether or not a fresh-connection factory is injected."""
    yield scope
