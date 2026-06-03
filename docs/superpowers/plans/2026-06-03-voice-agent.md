# Agent vocal (sous-projet 2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the conversation pipeline (STT → LLM → TTS) behind provider interfaces, with a real DeepSeek LLM, a CEFR-adapted prompt, and server-side transcript capture/persistence — fully unit-tested with fakes, and runnable end-to-end as a LiveKit Agent once external keys are available.

**Architecture:** Feature-first module `app/features/conversation/`. Each external dependency (speech-to-text, LLM, text-to-speech) sits behind a `typing.Protocol`, with an in-memory **fake** (default for dev/tests, no paid accounts) and a real implementation. The **DeepSeek** LLM is wired now (OpenAI-compatible API, `deepseek-chat`); STT/TTS/LiveKit get fakes until keys exist. A `ConversationPipeline` orchestrates one turn and records a `Transcript`; transcripts persist to PostgreSQL so the debrief service (sub-project 3) can read them. The actual LiveKit Agent worker is the final, credential-gated task.

**Tech Stack:** Python 3.12, openai SDK (pointed at DeepSeek), SQLAlchemy 2.0 async, pytest. LiveKit Agents SDK only in the final task.

---

## File Structure

```
backend/app/features/conversation/
  __init__.py
  messages.py             # Message + Transcript value objects
  prompt.py               # PromptBuilder (CEFR-adapted system prompt)
  pipeline.py             # ConversationPipeline orchestrator (stt->llm->tts + transcript)
  models.py               # Transcript ORM (persisted turns)
  repository.py           # TranscriptRepository (Protocol + SQLAlchemy)
  providers/
    __init__.py
    interfaces.py         # SttProvider, LlmProvider, TtsProvider (Protocols)
    fakes.py              # FakeStt/FakeLlm/FakeTts (dev + tests, no network)
    deepseek.py           # DeepSeekLlmProvider (real, openai SDK -> api.deepseek.com)
  agent.py                # LiveKit Agent worker entrypoint (final task, credential-gated)
backend/app/registry.py   # + import Transcript model
backend/app/config.py     # + DeepSeek + voice settings
backend/tests/unit/
  test_transcript.py
  test_prompt_builder.py
  test_conversation_pipeline.py
  test_deepseek_provider.py
backend/tests/
  test_transcript_repository.py   # integration (real test DB)
```

**Conventions:** paths relative to `backend/`. Run `uv run pytest -q`, `uv run ruff check .`, `uv run mypy app` after each task — all must stay green (CI enforces them).

---

### Task 1: Add dependencies + conversation config

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`

- [ ] **Step 1: Add the `openai` dependency**

In `backend/pyproject.toml`, add to the `dependencies` array (after `email-validator>=2.2`):
```toml
    "openai>=1.59",
```

- [ ] **Step 2: Install**

Run (from `backend/`):
```bash
uv sync
```
Expected: `openai` installs without error.

- [ ] **Step 3: Add voice settings to `backend/app/config.py`**

Insert these fields inside `class Settings` (after `cors_allow_origins`):
```python
    # Conversation / voice
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"  # V3, low-latency; NOT the slow "reasoner"
    voice_engine: str = "fake"  # "fake" (default, no keys) | "deepseek" | "livekit"
```

- [ ] **Step 4: Document them in `backend/.env.example`**

Append:
```bash
# Conversation / voice (DeepSeek = LLM stage; STT/TTS/LiveKit added when available)
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
VOICE_ENGINE=fake
```

- [ ] **Step 5: Verify config loads**

Run:
```bash
uv run python -c "from app.config import get_settings; print(get_settings().deepseek_model)"
```
Expected: prints `deepseek-chat`.

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/config.py backend/.env.example
git commit -m "chore(conversation): add openai dep + DeepSeek/voice settings"
```

---

### Task 2: Message + Transcript value objects (TDD)

**Files:**
- Create: `backend/app/features/conversation/__init__.py` (empty)
- Create: `backend/app/features/conversation/messages.py`
- Test: `backend/tests/unit/test_transcript.py`

- [ ] **Step 1: Write the failing test — `backend/tests/unit/test_transcript.py`**

```python
from app.features.conversation.messages import Message, Transcript


def test_transcript_records_turns_in_order():
    t = Transcript()
    t.add_user("hello")
    t.add_assistant("hi, how are you?")
    assert t.messages == [
        Message(role="user", content="hello"),
        Message(role="assistant", content="hi, how are you?"),
    ]


def test_transcript_to_dicts_for_persistence():
    t = Transcript()
    t.add_user("hello")
    assert t.to_dicts() == [{"role": "user", "content": "hello"}]


def test_transcript_is_empty_initially():
    assert Transcript().messages == []
```

- [ ] **Step 2: Run it — verify it fails**

Run: `uv run pytest tests/unit/test_transcript.py -v`
Expected: FAIL — module `app.features.conversation.messages` not found.

- [ ] **Step 3: Create `backend/app/features/conversation/__init__.py`** (empty) and `backend/app/features/conversation/messages.py`**

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Message:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class Transcript:
    messages: list[Message] = field(default_factory=list)

    def add_user(self, content: str) -> None:
        self.messages.append(Message(role="user", content=content))

    def add_assistant(self, content: str) -> None:
        self.messages.append(Message(role="assistant", content=content))

    def to_dicts(self) -> list[dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in self.messages]
```

- [ ] **Step 4: Run it — verify it passes**

Run: `uv run pytest tests/unit/test_transcript.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/features/conversation/__init__.py backend/app/features/conversation/messages.py backend/tests/unit/test_transcript.py
git commit -m "feat(conversation): Message + Transcript value objects (tested)"
```

---

### Task 3: Provider interfaces + fakes (TDD)

**Files:**
- Create: `backend/app/features/conversation/providers/__init__.py` (empty)
- Create: `backend/app/features/conversation/providers/interfaces.py`
- Create: `backend/app/features/conversation/providers/fakes.py`
- Test: `backend/tests/unit/test_conversation_pipeline.py` (fakes portion first)

- [ ] **Step 1: Write the failing test — `backend/tests/unit/test_conversation_pipeline.py`**

```python
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
```

- [ ] **Step 2: Run it — verify it fails**

Run: `uv run pytest tests/unit/test_conversation_pipeline.py -v`
Expected: FAIL — `app.features.conversation.providers.fakes` not found.

- [ ] **Step 3: Create `backend/app/features/conversation/providers/__init__.py`** (empty) and `interfaces.py`**

```python
from typing import Protocol

from app.features.conversation.messages import Message


class SttProvider(Protocol):
    async def transcribe(self, audio: bytes) -> str: ...


class LlmProvider(Protocol):
    async def complete(self, system_prompt: str, history: list[Message]) -> str: ...


class TtsProvider(Protocol):
    async def synthesize(self, text: str) -> bytes: ...
```

- [ ] **Step 4: Create `backend/app/features/conversation/providers/fakes.py`**

```python
from app.features.conversation.messages import Message


class FakeStt:
    """Returns scripted transcripts in order; repeats the last one when exhausted."""

    def __init__(self, transcripts: list[str] | None = None) -> None:
        self._transcripts = transcripts or ["(silence)"]
        self._i = 0

    async def transcribe(self, audio: bytes) -> str:
        text = self._transcripts[min(self._i, len(self._transcripts) - 1)]
        self._i += 1
        return text


class FakeLlm:
    """Deterministic reply that echoes the last user message (no network)."""

    async def complete(self, system_prompt: str, history: list[Message]) -> str:
        last_user = next(
            (m.content for m in reversed(history) if m.role == "user"), ""
        )
        return f"You said: {last_user}"


class FakeTts:
    """Encodes text to bytes — stands in for synthesized audio."""

    async def synthesize(self, text: str) -> bytes:
        return text.encode("utf-8")
```

- [ ] **Step 5: Run it — verify it passes**

Run: `uv run pytest tests/unit/test_conversation_pipeline.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/features/conversation/providers backend/tests/unit/test_conversation_pipeline.py
git commit -m "feat(conversation): provider interfaces + fakes (tested)"
```

---

### Task 4: CEFR-adapted prompt builder (TDD)

**Files:**
- Create: `backend/app/features/conversation/prompt.py`
- Test: `backend/tests/unit/test_prompt_builder.py`

- [ ] **Step 1: Write the failing test — `backend/tests/unit/test_prompt_builder.py`**

```python
from app.features.conversation.prompt import PromptContext, build_system_prompt


def test_prompt_includes_level_and_no_inline_correction_rule():
    prompt = build_system_prompt(
        PromptContext(cefr_level="A2", scenario_id=None, interests=[], memory_summary="")
    )
    assert "A2" in prompt
    # Pedagogy: never correct inline during the conversation (debrief is deferred).
    assert "do not correct" in prompt.lower()
    # Output hypothesis: keep the learner talking.
    assert "ask" in prompt.lower()


def test_prompt_includes_scenario_role_when_given():
    prompt = build_system_prompt(
        PromptContext(
            cefr_level="B1", scenario_id="restaurant", interests=["food"], memory_summary=""
        )
    )
    assert "restaurant" in prompt.lower()


def test_prompt_weaves_in_memory_summary():
    prompt = build_system_prompt(
        PromptContext(
            cefr_level="B1",
            scenario_id=None,
            interests=[],
            memory_summary="Last time we discussed the user's trip to Italy.",
        )
    )
    assert "Italy" in prompt
```

- [ ] **Step 2: Run it — verify it fails**

Run: `uv run pytest tests/unit/test_prompt_builder.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Create `backend/app/features/conversation/prompt.py`**

```python
from dataclasses import dataclass

# Coarse per-level guidance (comprehensible input / i+1).
_LEVEL_GUIDANCE = {
    "A1": "Use very simple words and short present-tense sentences. Speak slowly.",
    "A2": "Use simple everyday vocabulary and short sentences. Avoid idioms.",
    "B1": "Use common vocabulary and a mix of tenses. Introduce occasional new words.",
    "B2": "Use natural vocabulary and varied structures. Challenge the learner slightly.",
    "C1": "Use rich, idiomatic English at near-native pace.",
    "C2": "Use fully native, nuanced English.",
}


@dataclass(frozen=True)
class PromptContext:
    cefr_level: str
    scenario_id: str | None
    interests: list[str]
    memory_summary: str


def build_system_prompt(ctx: PromptContext) -> str:
    level = ctx.cefr_level.upper()
    guidance = _LEVEL_GUIDANCE.get(level, _LEVEL_GUIDANCE["B1"])

    parts = [
        "You are a warm, patient English-speaking partner for a language learner.",
        f"The learner's CEFR level is {level}. {guidance}",
        "Keep your turns short so the learner does most of the talking, and end most "
        "turns with an open question to keep the conversation going.",
        "Do NOT correct the learner's mistakes during the conversation; stay in the flow. "
        "Mistakes are reviewed afterwards in a separate debrief.",
        "Never switch to the learner's native language unless they are completely stuck.",
    ]
    if ctx.scenario_id:
        parts.append(f"Play your role in this scenario: {ctx.scenario_id}.")
    if ctx.interests:
        parts.append("The learner is interested in: " + ", ".join(ctx.interests) + ".")
    if ctx.memory_summary:
        parts.append("Context from previous conversations: " + ctx.memory_summary)
    return "\n".join(parts)
```

- [ ] **Step 4: Run it — verify it passes**

Run: `uv run pytest tests/unit/test_prompt_builder.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/features/conversation/prompt.py backend/tests/unit/test_prompt_builder.py
git commit -m "feat(conversation): CEFR-adapted system prompt builder (tested)"
```

---

### Task 5: ConversationPipeline orchestrator (TDD)

**Files:**
- Create: `backend/app/features/conversation/pipeline.py`
- Modify: `backend/tests/unit/test_conversation_pipeline.py` (append)

- [ ] **Step 1: Append the failing tests to `backend/tests/unit/test_conversation_pipeline.py`**

```python
from app.features.conversation.pipeline import ConversationPipeline


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
```

- [ ] **Step 2: Run — verify the new tests fail**

Run: `uv run pytest tests/unit/test_conversation_pipeline.py -v`
Expected: the 2 new tests FAIL (module/class not found); earlier 3 still pass.

- [ ] **Step 3: Create `backend/app/features/conversation/pipeline.py`**

```python
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
```

- [ ] **Step 4: Run — verify all pass**

Run: `uv run pytest tests/unit/test_conversation_pipeline.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/features/conversation/pipeline.py backend/tests/unit/test_conversation_pipeline.py
git commit -m "feat(conversation): ConversationPipeline orchestrator (tested)"
```

---

### Task 6: DeepSeek LLM provider (real, injectable client) (TDD)

**Files:**
- Create: `backend/app/features/conversation/providers/deepseek.py`
- Test: `backend/tests/unit/test_deepseek_provider.py`

- [ ] **Step 1: Write the failing test — `backend/tests/unit/test_deepseek_provider.py`**

The provider takes an injected async client, so we test message-mapping and parsing with a stub — no network, no key.

```python
import pytest

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
    def __init__(self, recorder):
        self._recorder = recorder

    async def create(self, *, model, messages):
        self._recorder["model"] = model
        self._recorder["messages"] = messages
        return _StubResponse("Bonjour back")


class _StubChat:
    def __init__(self, recorder):
        self.completions = _StubCompletions(recorder)


class _StubClient:
    def __init__(self, recorder):
        self.chat = _StubChat(recorder)


@pytest.mark.asyncio
async def test_deepseek_builds_messages_and_parses_reply():
    recorder: dict = {}
    provider = DeepSeekLlmProvider(client=_StubClient(recorder), model="deepseek-chat")

    reply = await provider.complete(
        "SYSTEM", [Message(role="user", content="hello")]
    )

    assert reply == "Bonjour back"
    assert recorder["model"] == "deepseek-chat"
    assert recorder["messages"][0] == {"role": "system", "content": "SYSTEM"}
    assert recorder["messages"][1] == {"role": "user", "content": "hello"}


@pytest.mark.asyncio
async def test_deepseek_returns_empty_string_when_content_is_none():
    provider = DeepSeekLlmProvider(client=_StubClient({}), model="deepseek-chat")

    # Force a None content response.
    class _NoneClient(_StubClient):
        def __init__(self):
            super().__init__({})

            async def create(*, model, messages):
                return _StubResponse(None)

            self.chat.completions.create = create  # type: ignore[assignment]

    provider2 = DeepSeekLlmProvider(client=_NoneClient(), model="deepseek-chat")
    assert await provider2.complete("s", [Message(role="user", content="x")]) == ""
```

- [ ] **Step 2: Run — verify it fails**

Run: `uv run pytest tests/unit/test_deepseek_provider.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Create `backend/app/features/conversation/providers/deepseek.py`**

```python
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
        messages = [{"role": "system", "content": system_prompt}]
        messages += [{"role": m.role, "content": m.content} for m in history]
        response = await self._client.chat.completions.create(
            model=self._model, messages=messages
        )
        return response.choices[0].message.content or ""


def build_deepseek_client(api_key: str, base_url: str) -> Any:
    """Construct the real DeepSeek (OpenAI-compatible) async client."""
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=api_key, base_url=base_url)
```

- [ ] **Step 4: Run — verify it passes**

Run: `uv run pytest tests/unit/test_deepseek_provider.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/features/conversation/providers/deepseek.py backend/tests/unit/test_deepseek_provider.py
git commit -m "feat(conversation): DeepSeek LLM provider, injectable + tested"
```

---

### Task 7: Transcript persistence — model, migration, repository (TDD)

**Files:**
- Create: `backend/app/features/conversation/models.py`
- Create: `backend/app/features/conversation/repository.py`
- Modify: `backend/app/registry.py`
- Create (generated): `backend/migrations/versions/<hash>_transcripts.py`
- Test: `backend/tests/test_transcript_repository.py`

- [ ] **Step 1: Create the ORM model `backend/app/features/conversation/models.py`**

```python
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sessions.id", ondelete="CASCADE"), unique=True, index=True
    )
    turns: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 2: Register it in `backend/app/registry.py`**

Replace the file contents with:
```python
"""Imports every ORM model so they register on Base.metadata."""

from app.database import Base
from app.features.auth.models import RefreshToken, User
from app.features.conversation.models import Transcript
from app.features.profile.models import LearnerProfile
from app.features.sessions.models import ConversationSession

__all__ = [
    "Base",
    "User",
    "RefreshToken",
    "LearnerProfile",
    "ConversationSession",
    "Transcript",
]
```

- [ ] **Step 3: Generate and apply the migration**

Run (from `backend/`, Docker Postgres up):
```bash
uv run alembic revision --autogenerate -m "transcripts"
uv run alembic upgrade head
```
Expected: a version file with `op.create_table("transcripts", ...)`; upgrade succeeds.

- [ ] **Step 4: Create the repository `backend/app/features/conversation/repository.py`**

```python
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.conversation.models import Transcript


class TranscriptRepository(Protocol):
    async def save(self, session_id: int, turns: list[dict]) -> Transcript: ...

    async def get_by_session(self, session_id: int) -> Transcript | None: ...


class SqlAlchemyTranscriptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, session_id: int, turns: list[dict]) -> Transcript:
        existing = await self.get_by_session(session_id)
        if existing is None:
            existing = Transcript(session_id=session_id, turns=turns)
            self._session.add(existing)
        else:
            existing.turns = turns
        await self._session.commit()
        await self._session.refresh(existing)
        return existing

    async def get_by_session(self, session_id: int) -> Transcript | None:
        return await self._session.scalar(
            select(Transcript).where(Transcript.session_id == session_id)
        )
```

- [ ] **Step 5: Write the integration test — `backend/tests/test_transcript_repository.py`**

```python
import pytest

from app.features.auth.models import User
from app.features.conversation.repository import SqlAlchemyTranscriptRepository
from app.features.sessions.models import ConversationSession


async def _make_session(db) -> int:
    user = User(email="t@b.com", hashed_password="x", native_language="fr")
    db.add(user)
    await db.flush()
    convo = ConversationSession(user_id=user.id, mode="free", room_name="apm-room-x")
    db.add(convo)
    await db.commit()
    await db.refresh(convo)
    return convo.id


@pytest.mark.asyncio
async def test_save_then_get_roundtrips_turns(db_session):
    session_id = await _make_session(db_session)
    repo = SqlAlchemyTranscriptRepository(db_session)

    turns = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
    await repo.save(session_id, turns)

    fetched = await repo.get_by_session(session_id)
    assert fetched is not None
    assert fetched.turns == turns


@pytest.mark.asyncio
async def test_save_is_idempotent_per_session(db_session):
    session_id = await _make_session(db_session)
    repo = SqlAlchemyTranscriptRepository(db_session)

    await repo.save(session_id, [{"role": "user", "content": "first"}])
    await repo.save(session_id, [{"role": "user", "content": "second"}])

    fetched = await repo.get_by_session(session_id)
    assert fetched is not None
    assert fetched.turns == [{"role": "user", "content": "second"}]
```

- [ ] **Step 6: Add a `db_session` fixture to `backend/tests/conftest.py`**

This test needs a raw DB session (not via HTTP). Append to `conftest.py`:
```python
@pytest_asyncio.fixture
async def db_session(_engine, _setup_db):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    maker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
```
And ensure the import line at the top of `conftest.py` includes `AsyncSession`:
```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
```
(It already imports `async_sessionmaker` and `create_async_engine`; add `AsyncSession` if missing.)

- [ ] **Step 7: Run — verify it passes**

Run: `uv run pytest tests/test_transcript_repository.py -v`
Expected: 2 passed.

- [ ] **Step 8: Commit**

```bash
git add backend/app/features/conversation/models.py backend/app/features/conversation/repository.py backend/app/registry.py backend/migrations/versions backend/tests/test_transcript_repository.py backend/tests/conftest.py
git commit -m "feat(conversation): transcript persistence (model+migration+repo, tested)"
```

---

### Task 8: Pipeline factory wiring (fake vs DeepSeek) (TDD)

**Files:**
- Create: `backend/app/features/conversation/factory.py`
- Test: `backend/tests/unit/test_conversation_factory.py`

- [ ] **Step 1: Write the failing test — `backend/tests/unit/test_conversation_factory.py`**

```python
from app.features.conversation.factory import build_llm_provider
from app.features.conversation.providers.deepseek import DeepSeekLlmProvider
from app.features.conversation.providers.fakes import FakeLlm


def test_factory_returns_fake_llm_by_default():
    assert isinstance(build_llm_provider(engine="fake", api_key="", base_url="", model="m"), FakeLlm)


def test_factory_returns_deepseek_when_engine_is_deepseek():
    provider = build_llm_provider(
        engine="deepseek", api_key="sk-test", base_url="https://api.deepseek.com", model="deepseek-chat"
    )
    assert isinstance(provider, DeepSeekLlmProvider)
```

- [ ] **Step 2: Run — verify it fails**

Run: `uv run pytest tests/unit/test_conversation_factory.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Create `backend/app/features/conversation/factory.py`**

```python
from app.features.conversation.providers.deepseek import (
    DeepSeekLlmProvider,
    build_deepseek_client,
)
from app.features.conversation.providers.fakes import FakeLlm
from app.features.conversation.providers.interfaces import LlmProvider


def build_llm_provider(engine: str, api_key: str, base_url: str, model: str) -> LlmProvider:
    """Select the LLM provider from config. Defaults to the fake (no keys needed)."""
    if engine == "deepseek":
        client = build_deepseek_client(api_key=api_key, base_url=base_url)
        return DeepSeekLlmProvider(client=client, model=model)
    return FakeLlm()
```

- [ ] **Step 4: Run — verify it passes**

Run: `uv run pytest tests/unit/test_conversation_factory.py -v`
Expected: 2 passed.

- [ ] **Step 5: Full gate + commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest -q
git add backend/app/features/conversation/factory.py backend/tests/unit/test_conversation_factory.py
git commit -m "feat(conversation): LLM provider factory (fake|deepseek, tested)"
```
Expected: all green.

---

### Task 9 (credential-gated): LiveKit Agent worker

> Run this task only once you have LiveKit Cloud + STT (Deepgram) + TTS (Cartesia/ElevenLabs) keys. It wires the real transport and real STT/TTS to the pipeline built above. Until then, Tasks 1–8 give a fully tested conversation core.

**Files:**
- Modify: `backend/pyproject.toml` (add `livekit-agents` + plugin deps)
- Create: `backend/app/features/conversation/agent.py`
- Modify: `backend/.env.example` (LiveKit/Deepgram/TTS keys)
- Create: `backend/app/features/conversation/providers/deepgram.py` (real STT)
- Create: `backend/app/features/conversation/providers/cartesia.py` (real TTS)

- [ ] **Step 1: Add LiveKit Agents dependencies**

In `backend/pyproject.toml` dependencies, add:
```toml
    "livekit-agents>=0.12",
    "livekit-plugins-deepgram>=0.6",
    "livekit-plugins-cartesia>=0.4",
    "livekit-plugins-openai>=0.10",
```
Run `uv sync`.

- [ ] **Step 2: Add the worker entrypoint `backend/app/features/conversation/agent.py`**

```python
"""LiveKit Agent worker.

Runs as a SEPARATE process: `uv run python -m app.features.conversation.agent`.
It joins the room created by the backend's /sessions/start, then runs an
STT -> LLM -> TTS voice pipeline. The LLM points at DeepSeek (OpenAI-compatible).
"""

from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli
from livekit.agents.voice import Agent, AgentSession
from livekit.plugins import cartesia, deepgram, openai

from app.config import get_settings


async def entrypoint(ctx: JobContext) -> None:
    settings = get_settings()
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    session = AgentSession(
        stt=deepgram.STT(),
        llm=openai.LLM(
            model=settings.deepseek_model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        ),
        tts=cartesia.TTS(),
    )
    await session.start(
        agent=Agent(instructions="You are a warm English-speaking partner."),
        room=ctx.room,
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
```

- [ ] **Step 3: Document keys in `backend/.env.example`**

```bash
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
LIVEKIT_URL=wss://your-project.livekit.cloud
DEEPGRAM_API_KEY=...
CARTESIA_API_KEY=...
VOICE_ENGINE=livekit
```

- [ ] **Step 4: Run the worker (live smoke test)**

With the backend running and a session started from the app/`/docs`:
```bash
uv run python -m app.features.conversation.agent dev
```
Expected: the worker connects to LiveKit and the agent speaks/responds in the room.

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/features/conversation/agent.py backend/.env.example
git commit -m "feat(conversation): LiveKit Agent worker (real STT/LLM/TTS)"
```

---

## Self-Review notes (coverage check)

- **Pipeline STT→LLM→TTS** → Tasks 3 (interfaces+fakes), 5 (orchestrator), 9 (real transport).
- **LLM via DeepSeek** → Tasks 6 (provider), 8 (factory), 9 (wired in worker).
- **Prompt adapté au niveau (CEFR/i+1)** → Task 4.
- **Capture du transcript** → Tasks 2 (value object), 7 (persistence).
- **Pas de correction inline** (pédagogie) → enforced in the prompt (Task 4) + tested.
- **Interfaces + fakes (testable sans comptes payants)** → Tasks 3, 6, 8.
- **Coût maîtrisé** → DeepSeek (cheap) as LLM; fakes by default; real providers only behind `VOICE_ENGINE`.

Out of scope here (later sub-projects): the debrief/grammar analysis reads `transcripts` (#3), memory summary that feeds `PromptContext.memory_summary` (#5), pronunciation scoring (#4). The `memory_summary` and `interests` are already accepted by `build_system_prompt` so #5 can populate them without changing this module.
```
