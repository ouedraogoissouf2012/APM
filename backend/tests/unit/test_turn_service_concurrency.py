"""Concurrency coverage for #289.

turn_service.py:189-194 fires the grammar correction for a turn via a bare
`asyncio.ensure_future` — a fire-and-forget Task running alongside the reply
stream. No existing test ever drove TWO of these concurrently, even though that
is exactly what production does: `conversation/factory.py` caches the LLM
provider process-wide (`shared_llm_provider`, an `lru_cache`), so every
concurrent request's correction call — and its reply call — actually run
through the SAME provider instance at once.

Two things the audit flagged as plausible failure modes for that setup:
  1. a mix-up — one learner's correction (or reply) leaking into another's
     stream, or a call getting silently dropped under concurrency
     (`test_concurrent_turns_with_correction_dont_interfere`);
  2. an over-eager cancellation — cancelling one learner's turn (client
     disconnect, a reply-stream error, ...) killing a DIFFERENT learner's
     still-running correction. `correction_task` is only ever cancelled from
     TWO places, and they need separate tests because they're reached via
     different mechanisms:
       - `await correction_task` (turn_service.py:240): cancelling a task
         that is suspended directly awaiting another task delegates the
         cancellation straight to that inner task (asyncio's own
         `_fut_waiter` propagation) — the `finally` block's own
         `correction_task.cancel()` never even runs on a live task in this
         case (`.done()` is already True by the time `finally` gets control).
         Covered by `test_cancelling_one_users_turn_...`.
       - the `finally` block's explicit `correction_task.cancel()`
         (turn_service.py:246-247) is the ONLY thing that stops a correction
         that's still pending while the reply loop itself is interrupted
         (still inside turn_service.py:178-194, before `correction_task` is
         ever awaited). Covered by
         `test_client_disconnect_mid_reply_cancels_only_its_own_...`.

Both scenarios share a single fake LLM across two independent
ConversationTurnService/TurnCorrector pairs — mirroring the DI topology in
conversation/dependencies.py (fresh corrector, fresh service, shared LLM) —
and run the two turns genuinely concurrently (asyncio.gather / asyncio.Task),
not sequentially.
"""

import asyncio
import json

import pytest

from app.features.auth.models import User
from app.features.conversation.correction import TurnCorrector
from app.features.conversation.turn_service import (
    ConversationTurnService,
    CorrectionReady,
    ReplyChunk,
)


class _FakeSessions:
    def __init__(self, owner_id: int) -> None:
        self._owner_id = owner_id

    async def get(self, session_id):
        class _S:
            user_id = self._owner_id
            scenario_id = None
            mission_id = None
            ended_at = None

        return _S()


class _FakeTranscripts:
    def __init__(self) -> None:
        self.saved = None

    async def get_by_session(self, session_id):
        return None

    async def save(self, session_id, turns):
        self.saved = (session_id, turns)


class _FakeProfiles:
    async def get_by_user_id(self, user_id):
        return None


def _user(user_id: int) -> User:
    u = User(email=f"user{user_id}@example.com", hashed_password="x", native_language="fr")
    u.id = user_id
    u.cefr_level = "A2"
    return u


def _service(llm, owner_id: int) -> ConversationTurnService:
    return ConversationTurnService(
        _FakeSessions(owner_id=owner_id),
        _FakeTranscripts(),
        _FakeProfiles(),
        llm,
        corrector=TurnCorrector(llm),
    )


def _correction_json(text: str) -> str:
    return json.dumps(
        {
            "has_error": True,
            "original": text,
            "correction": f"FIXED: {text}",
            "rule": f"rule-for::{text}",
        }
    )


async def _run_turn(service, session_id, user, text):
    return [event async for event in service.stream_turn(session_id, user, text)]


class _SharedLlm:
    """One instance backs BOTH users' reply stream and BOTH users' correction
    call — exactly what production's process-wide cached LLM provider does for
    concurrent requests. Replies/corrections are keyed off the learner's own
    utterance (never off call order), so a mix-up between the two concurrent
    callers shows up as a wrong payload, not a hang. `asyncio.sleep(0)` on both
    paths forces a real interleaving on the event loop instead of the two calls
    trivially resolving back-to-back.
    """

    def __init__(self) -> None:
        self.correction_calls: list[str] = []

    async def stream_complete(self, system_prompt, history):
        text = history[-1].content
        await asyncio.sleep(0)
        yield f"Reply to: {text}"

    async def complete(self, system_prompt, history):
        # TurnCorrector always sends exactly one user message: the learner's
        # utterance verbatim (correction.py:68).
        text = history[0].content
        self.correction_calls.append(text)
        await asyncio.sleep(0)
        return _correction_json(text)


@pytest.mark.asyncio
async def test_concurrent_turns_with_correction_dont_interfere():
    llm = _SharedLlm()
    service_a = _service(llm, owner_id=1)
    service_b = _service(llm, owner_id=2)

    events_a, events_b = await asyncio.gather(
        _run_turn(service_a, 101, _user(1), "A he go home yesterday"),
        _run_turn(service_b, 202, _user(2), "B she dont like it"),
    )

    # Both users completed: exactly one correction each, none swallowed.
    corrections_a = [e for e in events_a if isinstance(e, CorrectionReady)]
    corrections_b = [e for e in events_b if isinstance(e, CorrectionReady)]
    assert len(corrections_a) == 1
    assert len(corrections_b) == 1

    # Neither correction was swapped with the other user's.
    assert corrections_a[0].correction.original == "A he go home yesterday"
    assert corrections_b[0].correction.original == "B she dont like it"

    # The reply itself wasn't crossed either.
    assert [e.text for e in events_a if isinstance(e, ReplyChunk)] == [
        "Reply to: A he go home yesterday"
    ]
    assert [e.text for e in events_b if isinstance(e, ReplyChunk)] == [
        "Reply to: B she dont like it"
    ]

    # The shared LLM really did see BOTH correction calls.
    assert sorted(llm.correction_calls) == sorted(["A he go home yesterday", "B she dont like it"])


class _AwaitGatedLlm:
    """Each correction call blocks on an `asyncio.Event` so the test can
    deterministically observe "both corrections are genuinely in flight at
    once" before acting — no sleep-duration guesswork. Both replies resolve
    in a single sentence, so by the time a correction call starts, its
    request's `stream_prepared` generator is already suspended at
    `await correction_task` (turn_service.py:240) — there is nothing else
    left for it to do.
    """

    def __init__(self) -> None:
        self.a_started = asyncio.Event()
        self.a_release = asyncio.Event()
        self.b_started = asyncio.Event()
        self._b_stuck = asyncio.Event()  # never set: B's correction call hangs
        self.correction_calls: list[str] = []

    async def stream_complete(self, system_prompt, history):
        yield f"Reply to: {history[-1].content}"

    async def complete(self, system_prompt, history):
        text = history[0].content
        self.correction_calls.append(text)
        if text.startswith("A "):
            self.a_started.set()
            await self.a_release.wait()
        else:
            self.b_started.set()
            await self._b_stuck.wait()
        return _correction_json(text)


@pytest.mark.asyncio
async def test_cancelling_one_users_turn_while_it_awaits_its_correction_does_not_cancel_anothers():
    # Learner B disconnects (their whole request task is cancelled) at the
    # point where their OWN stream_prepared generator is suspended directly at
    # `await correction_task` (turn_service.py:240) — the reply was already
    # fully streamed and persisted, only the correction is still pending.
    # asyncio delivers that cancellation straight to the awaited task (a
    # task's `_fut_waiter` is cancelled first), so this exercises Python's own
    # await-cancellation propagation, NOT the `finally` block's explicit
    # `correction_task.cancel()` (that guard never runs against a live task
    # here: by the time `finally` gets control, `.done()` is already True).
    # Learner A's correction is independently in flight at the same moment —
    # proving the cancellation stays scoped to B's own task either way.
    llm = _AwaitGatedLlm()
    service_a = _service(llm, owner_id=1)
    service_b = _service(llm, owner_id=2)

    task_a = asyncio.create_task(_run_turn(service_a, 101, _user(1), "A he go home"))
    task_b = asyncio.create_task(_run_turn(service_b, 202, _user(2), "B she dont like it"))

    await asyncio.wait_for(llm.a_started.wait(), timeout=5)
    await asyncio.wait_for(llm.b_started.wait(), timeout=5)
    # Both corrections are now blocked mid-call — genuinely concurrent, not
    # sequential.

    task_b.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task_b, timeout=5)

    llm.a_release.set()  # let A's correction resolve
    events_a = await asyncio.wait_for(task_a, timeout=5)

    corrections_a = [e for e in events_a if isinstance(e, CorrectionReady)]
    assert len(corrections_a) == 1
    assert corrections_a[0].correction.original == "A he go home"


class _MidStreamCancelLlm:
    """B's reply stream hangs while generating its SECOND sentence — so
    turn_service.py has already created B's correction_task right after the
    first sentence (turn_service.py:189-194), but `stream_prepared` is still
    inside the reply loop (line 178), nowhere near `await correction_task`
    (line 240). Cancelling B from exactly here is the one state where the
    `finally` block's own `correction_task.cancel()` (turn_service.py:
    246-247) is what actually stops it, instead of asyncio's
    cancel-propagates-through-a-direct-await mechanism. A's correction is
    independently gated to prove it is genuinely still in flight (not just
    already finished) when B is cancelled.
    """

    def __init__(self) -> None:
        self.a_started = asyncio.Event()
        self.a_release = asyncio.Event()
        self.b_correction_started = asyncio.Event()
        self.b_correction_cancelled = asyncio.Event()
        self._b_second_sentence_stuck = asyncio.Event()  # never set
        self._b_correction_stuck = asyncio.Event()  # never set

    async def stream_complete(self, system_prompt, history):
        text = history[-1].content
        yield f"Reply to: {text}"
        if text.startswith("B "):
            await self._b_second_sentence_stuck.wait()

    async def complete(self, system_prompt, history):
        text = history[0].content
        if text.startswith("A "):
            self.a_started.set()
            await self.a_release.wait()
        else:
            self.b_correction_started.set()
            try:
                await self._b_correction_stuck.wait()
            except asyncio.CancelledError:
                self.b_correction_cancelled.set()
                raise
        return _correction_json(text)


@pytest.mark.asyncio
async def test_client_disconnect_mid_reply_cancels_only_its_own_pending_correction():
    llm = _MidStreamCancelLlm()
    service_a = _service(llm, owner_id=1)
    service_b = _service(llm, owner_id=2)

    task_a = asyncio.create_task(_run_turn(service_a, 101, _user(1), "A he go home"))
    task_b = asyncio.create_task(_run_turn(service_b, 202, _user(2), "B she dont like it"))

    await asyncio.wait_for(llm.a_started.wait(), timeout=5)
    await asyncio.wait_for(llm.b_correction_started.wait(), timeout=5)
    # A's correction is genuinely in flight (blocked on a_release). B's
    # correction_task exists and is running too, but B's stream_prepared is
    # still stuck generating its reply's 2nd sentence — it has not reached
    # `await correction_task` yet.

    task_b.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task_b, timeout=5)
    # Proves the `finally` block's explicit cancel actually fired on B's task.
    await asyncio.wait_for(llm.b_correction_cancelled.wait(), timeout=5)

    llm.a_release.set()
    events_a = await asyncio.wait_for(task_a, timeout=5)

    corrections_a = [e for e in events_a if isinstance(e, CorrectionReady)]
    assert len(corrections_a) == 1
    assert corrections_a[0].correction.original == "A he go home"
