# Service bilan (grammaire + CEFR) — sous-projet 3 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** From a stored conversation transcript, produce a learner debrief — a list of `mistake → rule → correction` (explained in the learner's native language) plus a CEFR estimate — using an LLM (DeepSeek behind the `LlmProvider` interface), with deterministic anti-hallucination grounding, persisted and exposed over the API.

**Architecture:** New feature-first module `app/features/debrief/`. A `DebriefAnalyzer` depends only on the existing `LlmProvider` Protocol (fake in tests, DeepSeek in prod). It prompts for strict JSON, parses robustly, and **drops any "mistake" whose original text does not actually appear in the learner's utterances** (the key anti-hallucination guard). Results persist to a `debriefs` table (one per session) and are served via `POST/GET /sessions/{id}/debrief`. ERRANT-based error typing is deliberately deferred (heavy spaCy dependency) — tracked as a follow-up.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, the existing `app/features/conversation` provider abstraction, pytest.

---

## File Structure

```
backend/app/features/debrief/
  __init__.py
  domain.py            # DebriefError, DebriefResult value objects + VALID_CEFR
  parsing.py           # extract_json + parse_debrief_json (robust LLM-output parsing)
  analyzer.py          # DebriefAnalyzer (LlmProvider -> DebriefResult, span-grounded)
  models.py            # Debrief ORM (one per session)
  repository.py        # DebriefRepository (Protocol + SQLAlchemy)
  schemas.py           # DebriefOut / DebriefErrorOut (API DTOs)
  service.py           # DebriefService (read transcript -> analyze -> persist)
  dependencies.py      # get_debrief_service + wiring
  router.py            # POST/GET /sessions/{id}/debrief
backend/app/domain/exceptions.py   # + DebriefAnalysisError
backend/app/api/errors.py          # + map DebriefAnalysisError -> 502
backend/app/config.py              # + debrief_engine
backend/app/registry.py            # + Debrief model
backend/app/main.py                # + include debrief router
backend/tests/unit/test_debrief_parsing.py
backend/tests/unit/test_debrief_analyzer.py
backend/tests/test_debrief_repository.py      # integration
backend/tests/test_debrief_api.py             # integration
```

**Conventions:** paths relative to `backend/`. After each task run the gates (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy app`, `uv run pytest -q`) — all must pass (CI enforces them). PostgreSQL runs in Docker on host port 5434 (up).

---

### Task 1: Add `debrief_engine` config

**Files:** Modify `backend/app/config.py`, `backend/.env.example`.

- [ ] **Step 1: Add the field to `class Settings` in `backend/app/config.py`**, right after the `voice_engine` field:
```python
    debrief_engine: str = "fake"  # "fake" (default, no keys) | "deepseek"
```

- [ ] **Step 2: Document it in `backend/.env.example`**, under the Conversation/voice section:
```bash
DEBRIEF_ENGINE=fake
```

- [ ] **Step 3: Verify** — run `uv run python -c "from app.config import get_settings; print(get_settings().debrief_engine)"`. Expected: `fake`.

- [ ] **Step 4: Commit**
```bash
git add backend/app/config.py backend/.env.example
git commit -m "chore(debrief): add debrief_engine setting"
```

---

### Task 2: Debrief domain value objects (TDD)

**Files:** Create `backend/app/features/debrief/__init__.py` (empty), `backend/app/features/debrief/domain.py`; Test `backend/tests/unit/test_debrief_analyzer.py` (domain portion first — but put domain-only asserts in a small test that we extend later; for now create `test_debrief_domain` inline in the analyzer test file is fine. To keep it simple, test in the parsing test file is wrong — create the value objects and a tiny test here).

- [ ] **Step 1: Write the failing test — create `backend/tests/unit/test_debrief_domain.py`**
```python
from app.features.debrief.domain import VALID_CEFR, DebriefError, DebriefResult


def test_debrief_error_holds_fields():
    e = DebriefError(
        original="I go yesterday",
        correction="I went yesterday",
        rule="Past simple",
        error_type="verb_tense",
    )
    assert e.original == "I go yesterday"
    assert e.correction == "I went yesterday"


def test_debrief_result_defaults_to_empty_errors():
    r = DebriefResult(cefr_estimate="B1", summary="ok")
    assert r.errors == []


def test_valid_cefr_set():
    assert VALID_CEFR == {"A1", "A2", "B1", "B2", "C1", "C2"}
```

- [ ] **Step 2: Run — verify it fails** (`uv run pytest tests/unit/test_debrief_domain.py -v`): module not found.

- [ ] **Step 3: Create `backend/app/features/debrief/__init__.py`** (empty) and `backend/app/features/debrief/domain.py`:
```python
from dataclasses import dataclass, field

VALID_CEFR = {"A1", "A2", "B1", "B2", "C1", "C2"}


@dataclass(frozen=True)
class DebriefError:
    original: str
    correction: str
    rule: str
    error_type: str


@dataclass
class DebriefResult:
    cefr_estimate: str
    summary: str
    errors: list[DebriefError] = field(default_factory=list)
```

- [ ] **Step 4: Run — verify 3 passed.**

- [ ] **Step 5: Commit**
```bash
git add backend/app/features/debrief/__init__.py backend/app/features/debrief/domain.py backend/tests/unit/test_debrief_domain.py
git commit -m "feat(debrief): domain value objects (tested)"
```

---

### Task 3: Robust JSON parsing of LLM output (TDD)

**Files:** Create `backend/app/features/debrief/parsing.py`; add `DebriefAnalysisError` to `backend/app/domain/exceptions.py`; Test `backend/tests/unit/test_debrief_parsing.py`.

- [ ] **Step 1: Add the exception to `backend/app/domain/exceptions.py`** (append after the last exception class):
```python
class DebriefAnalysisError(DomainError):
    """The debrief LLM returned output that could not be parsed."""
```

- [ ] **Step 2: Write the failing test — `backend/tests/unit/test_debrief_parsing.py`**
```python
import pytest

from app.domain.exceptions import DebriefAnalysisError
from app.features.debrief.parsing import parse_debrief_json


def test_parses_plain_json():
    data = parse_debrief_json('{"cefr_estimate": "B1", "summary": "good", "errors": []}')
    assert data["cefr_estimate"] == "B1"
    assert data["errors"] == []


def test_parses_json_wrapped_in_markdown_fences():
    raw = '```json\n{"cefr_estimate": "A2", "summary": "ok", "errors": []}\n```'
    data = parse_debrief_json(raw)
    assert data["cefr_estimate"] == "A2"


def test_parses_json_with_surrounding_prose():
    raw = 'Here is the analysis: {"cefr_estimate": "B2", "summary": "s", "errors": []} Thanks!'
    data = parse_debrief_json(raw)
    assert data["cefr_estimate"] == "B2"


def test_raises_on_unparseable_output():
    with pytest.raises(DebriefAnalysisError):
        parse_debrief_json("sorry, I cannot help with that")
```

- [ ] **Step 3: Run — verify it fails.**

- [ ] **Step 4: Create `backend/app/features/debrief/parsing.py`**
```python
import json
from typing import Any

from app.domain.exceptions import DebriefAnalysisError


def _extract_json_object(text: str) -> str:
    """Return the substring from the first '{' to the last '}' (handles code fences/prose)."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise DebriefAnalysisError("No JSON object found in LLM output")
    return text[start : end + 1]


def parse_debrief_json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(_extract_json_object(text))
    except json.JSONDecodeError as exc:
        raise DebriefAnalysisError(f"Invalid JSON from debrief LLM: {exc}") from exc
    if not isinstance(data, dict):
        raise DebriefAnalysisError("Debrief LLM output is not a JSON object")
    return data
```

- [ ] **Step 5: Run — verify 4 passed.**

- [ ] **Step 6: Commit**
```bash
git add backend/app/domain/exceptions.py backend/app/features/debrief/parsing.py backend/tests/unit/test_debrief_parsing.py
git commit -m "feat(debrief): robust LLM JSON parsing + DebriefAnalysisError (tested)"
```

---

### Task 4: DebriefAnalyzer with span-grounding (TDD)

**Files:** Create `backend/app/features/debrief/analyzer.py`; Test `backend/tests/unit/test_debrief_analyzer.py`.

- [ ] **Step 1: Write the failing test — `backend/tests/unit/test_debrief_analyzer.py`**

The analyzer depends on the existing `LlmProvider` Protocol (`async complete(system_prompt, history) -> str`). We inject a fake returning canned JSON.

```python
import pytest

from app.features.conversation.messages import Message
from app.features.debrief.analyzer import DebriefAnalyzer


class _CannedLlm:
    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.seen_system: str | None = None
        self.seen_user: str | None = None

    async def complete(self, system_prompt: str, history: list[Message]) -> str:
        self.seen_system = system_prompt
        self.seen_user = history[-1].content if history else ""
        return self._reply


_TURNS = [
    {"role": "assistant", "content": "How was your day?"},
    {"role": "user", "content": "I go to school yesterday and i eats lunch"},
]


@pytest.mark.asyncio
async def test_analyze_returns_errors_and_cefr():
    reply = (
        '{"cefr_estimate": "A2", "summary": "Good effort!",'
        ' "errors": ['
        '  {"original": "I go to school yesterday", "correction": "I went to school yesterday",'
        '   "rule": "Past simple for finished actions", "error_type": "verb_tense"}'
        ' ]}'
    )
    analyzer = DebriefAnalyzer(_CannedLlm(reply))
    result = await analyzer.analyze(_TURNS, native_language="fr")

    assert result.cefr_estimate == "A2"
    assert result.summary == "Good effort!"
    assert len(result.errors) == 1
    assert result.errors[0].correction == "I went to school yesterday"


@pytest.mark.asyncio
async def test_analyze_drops_hallucinated_errors_not_in_learner_text():
    # The "original" never appears in the learner's utterances -> must be dropped.
    reply = (
        '{"cefr_estimate": "B1", "summary": "s",'
        ' "errors": ['
        '  {"original": "I have went to Paris", "correction": "I have gone to Paris",'
        '   "rule": "Past participle", "error_type": "verb_form"}'
        ' ]}'
    )
    analyzer = DebriefAnalyzer(_CannedLlm(reply))
    result = await analyzer.analyze(_TURNS, native_language="fr")
    assert result.errors == []  # hallucinated error grounded out


@pytest.mark.asyncio
async def test_analyze_falls_back_on_invalid_cefr():
    reply = '{"cefr_estimate": "Z9", "summary": "s", "errors": []}'
    analyzer = DebriefAnalyzer(_CannedLlm(reply))
    result = await analyzer.analyze(_TURNS, native_language="fr", fallback_cefr="A1")
    assert result.cefr_estimate == "A1"


@pytest.mark.asyncio
async def test_analyze_passes_native_language_into_prompt():
    analyzer = DebriefAnalyzer(_CannedLlm('{"cefr_estimate": "B1", "summary": "", "errors": []}'))
    await analyzer.analyze(_TURNS, native_language="fr")
    assert "fr" in analyzer._llm.seen_system  # type: ignore[attr-defined]
    # Only the learner's utterances are sent for analysis.
    assert "I go to school yesterday" in analyzer._llm.seen_user  # type: ignore[attr-defined]
    assert "How was your day?" not in analyzer._llm.seen_user  # type: ignore[attr-defined]
```

- [ ] **Step 2: Run — verify it fails.**

- [ ] **Step 3: Create `backend/app/features/debrief/analyzer.py`**
```python
from app.features.conversation.messages import Message
from app.features.conversation.providers.interfaces import LlmProvider
from app.features.debrief.domain import VALID_CEFR, DebriefError, DebriefResult
from app.features.debrief.parsing import parse_debrief_json


def _build_system_prompt(native_language: str, max_errors: int) -> str:
    return (
        "You are an English teacher analyzing a learner's spoken utterances. "
        f"Reply with ONLY a JSON object (no prose) in the language code '{native_language}' "
        "for all explanations. Schema: "
        '{"cefr_estimate": "<A1|A2|B1|B2|C1|C2>", "summary": "<short overall feedback>", '
        '"errors": [{"original": "<exact substring of the learner text>", '
        '"correction": "<fixed version>", "rule": "<grammar rule>", '
        '"error_type": "<short category>"}]}. '
        f"Report at most {max_errors} of the most useful errors. "
        "Each 'original' MUST be copied verbatim from the learner's text."
    )


class DebriefAnalyzer:
    def __init__(self, llm: LlmProvider, max_errors: int = 5) -> None:
        self._llm = llm
        self._max_errors = max_errors

    async def analyze(
        self,
        turns: list[dict],
        native_language: str,
        fallback_cefr: str = "A1",
    ) -> DebriefResult:
        learner_text = "\n".join(t["content"] for t in turns if t.get("role") == "user")
        system_prompt = _build_system_prompt(native_language, self._max_errors)
        raw = await self._llm.complete(system_prompt, [Message(role="user", content=learner_text)])
        data = parse_debrief_json(raw)

        cefr = data.get("cefr_estimate", "")
        if cefr not in VALID_CEFR:
            cefr = fallback_cefr

        errors: list[DebriefError] = []
        for item in data.get("errors", [])[: self._max_errors]:
            original = str(item.get("original", ""))
            # Anti-hallucination: keep only errors grounded in the actual learner text.
            if original and original in learner_text:
                errors.append(
                    DebriefError(
                        original=original,
                        correction=str(item.get("correction", "")),
                        rule=str(item.get("rule", "")),
                        error_type=str(item.get("error_type", "")),
                    )
                )

        return DebriefResult(
            cefr_estimate=cefr, summary=str(data.get("summary", "")), errors=errors
        )
```

- [ ] **Step 4: Run — verify 4 passed.**

- [ ] **Step 5: Commit**
```bash
git add backend/app/features/debrief/analyzer.py backend/tests/unit/test_debrief_analyzer.py
git commit -m "feat(debrief): DebriefAnalyzer with span-grounding anti-hallucination (tested)"
```

---

### Task 5: Debrief model, migration, repository (TDD)

**Files:** Create `backend/app/features/debrief/models.py`, `backend/app/features/debrief/repository.py`; Modify `backend/app/registry.py`; Create migration; Test `backend/tests/test_debrief_repository.py`.

- [ ] **Step 1: Create `backend/app/features/debrief/models.py`**
```python
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Debrief(Base):
    __tablename__ = "debriefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sessions.id", ondelete="CASCADE"), unique=True, index=True
    )
    cefr_estimate: Mapped[str] = mapped_column(String(2), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    errors: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 2: Register it in `backend/app/registry.py`** — replace contents with:
```python
"""Imports every ORM model so they register on Base.metadata."""

from app.database import Base
from app.features.auth.models import RefreshToken, User
from app.features.conversation.models import Transcript
from app.features.debrief.models import Debrief
from app.features.profile.models import LearnerProfile
from app.features.sessions.models import ConversationSession

__all__ = [
    "Base",
    "User",
    "RefreshToken",
    "LearnerProfile",
    "ConversationSession",
    "Transcript",
    "Debrief",
]
```

- [ ] **Step 3: Generate + apply migration** (from backend/):
```bash
uv run alembic revision --autogenerate -m "debriefs"
uv run alembic upgrade head
```
Expected: a version file with `op.create_table("debriefs", ...)` and only that table. If anything else appears, STOP and report.

- [ ] **Step 4: Create `backend/app/features/debrief/repository.py`**
```python
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.debrief.models import Debrief


class DebriefRepository(Protocol):
    async def save(
        self, session_id: int, cefr_estimate: str, summary: str, errors: list[dict]
    ) -> Debrief: ...

    async def get_by_session(self, session_id: int) -> Debrief | None: ...


class SqlAlchemyDebriefRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(
        self, session_id: int, cefr_estimate: str, summary: str, errors: list[dict]
    ) -> Debrief:
        existing = await self.get_by_session(session_id)
        if existing is None:
            existing = Debrief(
                session_id=session_id, cefr_estimate=cefr_estimate, summary=summary, errors=errors
            )
            self._session.add(existing)
        else:
            existing.cefr_estimate = cefr_estimate
            existing.summary = summary
            existing.errors = errors
        await self._session.commit()
        await self._session.refresh(existing)
        return existing

    async def get_by_session(self, session_id: int) -> Debrief | None:
        return await self._session.scalar(
            select(Debrief).where(Debrief.session_id == session_id)
        )
```

- [ ] **Step 5: Write the integration test — `backend/tests/test_debrief_repository.py`**
```python
import pytest

from app.features.auth.models import User
from app.features.debrief.repository import SqlAlchemyDebriefRepository
from app.features.sessions.models import ConversationSession


async def _make_session(db) -> int:
    user = User(email="d@b.com", hashed_password="x", native_language="fr")
    db.add(user)
    await db.flush()
    convo = ConversationSession(user_id=user.id, mode="free", room_name="apm-room-d")
    db.add(convo)
    await db.commit()
    await db.refresh(convo)
    return convo.id


@pytest.mark.asyncio
async def test_save_then_get_roundtrips(db_session):
    session_id = await _make_session(db_session)
    repo = SqlAlchemyDebriefRepository(db_session)
    errors = [{"original": "i go", "correction": "I go", "rule": "Capital I", "error_type": "spelling"}]

    await repo.save(session_id, "A2", "nice", errors)

    fetched = await repo.get_by_session(session_id)
    assert fetched is not None
    assert fetched.cefr_estimate == "A2"
    assert fetched.errors == errors


@pytest.mark.asyncio
async def test_save_is_idempotent_per_session(db_session):
    session_id = await _make_session(db_session)
    repo = SqlAlchemyDebriefRepository(db_session)
    await repo.save(session_id, "A2", "first", [])
    await repo.save(session_id, "B1", "second", [])
    fetched = await repo.get_by_session(session_id)
    assert fetched is not None
    assert fetched.cefr_estimate == "B1"
    assert fetched.summary == "second"
```

- [ ] **Step 6: Run** `uv run pytest tests/test_debrief_repository.py -v`. Expected: 2 passed. (`db_session` fixture already exists in `conftest.py` from sub-project 2.)

- [ ] **Step 7: Commit**
```bash
git add backend/app/features/debrief/models.py backend/app/features/debrief/repository.py backend/app/registry.py backend/migrations/versions backend/tests/test_debrief_repository.py
git commit -m "feat(debrief): Debrief model + migration + repository (tested)"
```

---

### Task 6: DebriefService + dependencies (TDD)

**Files:** Create `backend/app/features/debrief/service.py`, `backend/app/features/debrief/dependencies.py`; Test `backend/tests/unit/test_debrief_service.py`.

- [ ] **Step 1: Write the failing test — `backend/tests/unit/test_debrief_service.py`**

The service orchestrates: verify the session belongs to the user, read its transcript, analyze, persist. We test with in-memory fakes.

```python
import pytest

from app.domain.exceptions import NotFoundError
from app.features.auth.models import User
from app.features.debrief.analyzer import DebriefAnalyzer
from app.features.debrief.domain import DebriefResult
from app.features.debrief.service import DebriefService


class _FakeSessions:
    def __init__(self, owner_id: int | None) -> None:
        self._owner_id = owner_id

    async def get(self, session_id):
        if self._owner_id is None:
            return None

        class _S:
            user_id = self._owner_id

        return _S()


class _FakeTranscripts:
    def __init__(self, turns) -> None:
        self._turns = turns

    async def get_by_session(self, session_id):
        if self._turns is None:
            return None

        class _T:
            turns = self._turns

        return _T()


class _FakeDebriefs:
    def __init__(self) -> None:
        self.saved = None

    async def save(self, session_id, cefr_estimate, summary, errors):
        self.saved = (session_id, cefr_estimate, summary, errors)

        class _D:
            pass

        d = _D()
        d.session_id, d.cefr_estimate, d.summary, d.errors = (
            session_id, cefr_estimate, summary, errors,
        )
        return d

    async def get_by_session(self, session_id):
        return None


class _CannedLlm:
    async def complete(self, system_prompt, history):
        return '{"cefr_estimate": "B1", "summary": "ok", "errors": []}'


def _user() -> User:
    u = User(email="u@b.com", hashed_password="x", native_language="fr")
    u.id = 7
    return u


def _service(owner_id, turns, debriefs):
    return DebriefService(
        sessions=_FakeSessions(owner_id),
        transcripts=_FakeTranscripts(turns),
        debriefs=debriefs,
        analyzer=DebriefAnalyzer(_CannedLlm()),
    )


@pytest.mark.asyncio
async def test_generate_analyzes_and_persists():
    debriefs = _FakeDebriefs()
    service = _service(owner_id=7, turns=[{"role": "user", "content": "i is happy"}], debriefs=debriefs)
    result = await service.generate(session_id=1, user=_user())
    assert result.cefr_estimate == "B1"
    assert debriefs.saved is not None  # persisted


@pytest.mark.asyncio
async def test_generate_rejects_session_not_owned_by_user():
    service = _service(owner_id=999, turns=[{"role": "user", "content": "x"}], debriefs=_FakeDebriefs())
    with pytest.raises(NotFoundError):
        await service.generate(session_id=1, user=_user())


@pytest.mark.asyncio
async def test_generate_rejects_when_no_transcript():
    service = _service(owner_id=7, turns=None, debriefs=_FakeDebriefs())
    with pytest.raises(NotFoundError):
        await service.generate(session_id=1, user=_user())
```

- [ ] **Step 2: Run — verify it fails.**

- [ ] **Step 3: Create `backend/app/features/debrief/service.py`**
```python
from typing import Any

from app.domain.exceptions import NotFoundError
from app.features.auth.models import User
from app.features.debrief.analyzer import DebriefAnalyzer


class DebriefService:
    def __init__(
        self,
        sessions: Any,
        transcripts: Any,
        debriefs: Any,
        analyzer: DebriefAnalyzer,
    ) -> None:
        self._sessions = sessions
        self._transcripts = transcripts
        self._debriefs = debriefs
        self._analyzer = analyzer

    async def _owned_session(self, session_id: int, user: User) -> None:
        session = await self._sessions.get(session_id)
        if session is None or session.user_id != user.id:
            raise NotFoundError("Session not found")

    async def generate(self, session_id: int, user: User) -> Any:
        await self._owned_session(session_id, user)
        transcript = await self._transcripts.get_by_session(session_id)
        if transcript is None:
            raise NotFoundError("No transcript for this session")
        result = await self._analyzer.analyze(transcript.turns, native_language=user.native_language)
        errors = [
            {
                "original": e.original,
                "correction": e.correction,
                "rule": e.rule,
                "error_type": e.error_type,
            }
            for e in result.errors
        ]
        return await self._debriefs.save(
            session_id, result.cefr_estimate, result.summary, errors
        )

    async def get(self, session_id: int, user: User) -> Any:
        await self._owned_session(session_id, user)
        debrief = await self._debriefs.get_by_session(session_id)
        if debrief is None:
            raise NotFoundError("No debrief for this session")
        return debrief
```

- [ ] **Step 4: Run — verify 3 passed.**

- [ ] **Step 5: Create `backend/app/features/debrief/dependencies.py`**
```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.features.conversation.factory import build_llm_provider
from app.features.conversation.repository import SqlAlchemyTranscriptRepository
from app.features.debrief.analyzer import DebriefAnalyzer
from app.features.debrief.repository import SqlAlchemyDebriefRepository
from app.features.debrief.service import DebriefService
from app.features.sessions.repository import SqlAlchemySessionRepository


def get_debrief_service(db: AsyncSession = Depends(get_db)) -> DebriefService:
    settings = get_settings()
    llm = build_llm_provider(
        engine=settings.debrief_engine,
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
    )
    return DebriefService(
        sessions=SqlAlchemySessionRepository(db),
        transcripts=SqlAlchemyTranscriptRepository(db),
        debriefs=SqlAlchemyDebriefRepository(db),
        analyzer=DebriefAnalyzer(llm),
    )
```

- [ ] **Step 6: Commit**
```bash
git add backend/app/features/debrief/service.py backend/app/features/debrief/dependencies.py backend/tests/unit/test_debrief_service.py
git commit -m "feat(debrief): DebriefService + DI wiring (tested)"
```

---

### Task 7: API router + error mapping + wiring (TDD)

**Files:** Create `backend/app/features/debrief/schemas.py`, `backend/app/features/debrief/router.py`; Modify `backend/app/api/errors.py`, `backend/app/main.py`; Test `backend/tests/test_debrief_api.py`.

- [ ] **Step 1: Map `DebriefAnalysisError` → 502 in `backend/app/api/errors.py`**

Add to the imports from `app.domain.exceptions`: `DebriefAnalysisError`. Then add an entry to `_STATUS_BY_EXCEPTION` BEFORE the `(DomainError, ...)` fallback line:
```python
    (DebriefAnalysisError, status.HTTP_502_BAD_GATEWAY),
```

- [ ] **Step 2: Create `backend/app/features/debrief/schemas.py`**
```python
from pydantic import BaseModel


class DebriefErrorOut(BaseModel):
    original: str
    correction: str
    rule: str
    error_type: str


class DebriefOut(BaseModel):
    session_id: int
    cefr_estimate: str
    summary: str
    errors: list[DebriefErrorOut]

    model_config = {"from_attributes": True}
```

- [ ] **Step 3: Create `backend/app/features/debrief/router.py`**
```python
from fastapi import APIRouter, Depends, status

from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.debrief.dependencies import get_debrief_service
from app.features.debrief.schemas import DebriefOut
from app.features.debrief.service import DebriefService

router = APIRouter(prefix="/sessions/{session_id}/debrief", tags=["debrief"])


@router.post("", response_model=DebriefOut, status_code=status.HTTP_201_CREATED)
async def generate_debrief(
    session_id: int,
    current_user: User = Depends(get_current_user),
    service: DebriefService = Depends(get_debrief_service),
) -> DebriefOut:
    debrief = await service.generate(session_id, current_user)
    return DebriefOut.model_validate(debrief)


@router.get("", response_model=DebriefOut)
async def get_debrief(
    session_id: int,
    current_user: User = Depends(get_current_user),
    service: DebriefService = Depends(get_debrief_service),
) -> DebriefOut:
    debrief = await service.get(session_id, current_user)
    return DebriefOut.model_validate(debrief)
```

- [ ] **Step 4: Wire the router in `backend/app/main.py`**

Add the import alongside the other feature routers:
```python
from app.features.debrief.router import router as debrief_router
```
And add after the sessions router include:
```python
app.include_router(debrief_router)
```

- [ ] **Step 5: Write the integration test — `backend/tests/test_debrief_api.py`**

`DEBRIEF_ENGINE` defaults to `fake`, so the analyzer uses `FakeLlm` — whose reply is `"You said: <text>"`, which is NOT valid JSON. So for the API test we must drive a deterministic debrief. Override the debrief service dependency with one using a canned-JSON LLM.

```python
import pytest

from app.features.conversation.repository import SqlAlchemyTranscriptRepository
from app.features.debrief.analyzer import DebriefAnalyzer
from app.features.debrief.dependencies import get_debrief_service
from app.features.debrief.repository import SqlAlchemyDebriefRepository
from app.features.debrief.service import DebriefService
from app.features.sessions.repository import SqlAlchemySessionRepository
from app.main import app


class _CannedLlm:
    async def complete(self, system_prompt, history):
        return (
            '{"cefr_estimate": "A2", "summary": "Nice work",'
            ' "errors": [{"original": "i is happy", "correction": "I am happy",'
            ' "rule": "Subject-verb agreement", "error_type": "grammar"}]}'
        )


async def _register(client, email="dbg@b.com"):
    resp = await client.post("/auth/register", json={"email": email, "password": "s3cret!"})
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_generate_and_get_debrief(client, db_session):
    token = await _register(client)
    headers = {"Authorization": f"Bearer {token}"}

    # Start a session, end it, and store a transcript directly.
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]
    await SqlAlchemyTranscriptRepository(db_session).save(
        session_id, [{"role": "user", "content": "i is happy"}]
    )

    # Override the debrief service to use a deterministic JSON LLM.
    def _override():
        return DebriefService(
            sessions=SqlAlchemySessionRepository(db_session),
            transcripts=SqlAlchemyTranscriptRepository(db_session),
            debriefs=SqlAlchemyDebriefRepository(db_session),
            analyzer=DebriefAnalyzer(_CannedLlm()),
        )

    app.dependency_overrides[get_debrief_service] = _override
    try:
        created = await client.post(f"/sessions/{session_id}/debrief", headers=headers)
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["cefr_estimate"] == "A2"
        assert body["errors"][0]["correction"] == "I am happy"

        fetched = await client.get(f"/sessions/{session_id}/debrief", headers=headers)
        assert fetched.status_code == 200
        assert fetched.json()["summary"] == "Nice work"
    finally:
        app.dependency_overrides.pop(get_debrief_service, None)


@pytest.mark.asyncio
async def test_get_debrief_404_when_absent(client):
    token = await _register(client, email="dbg2@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]
    resp = await client.get(f"/sessions/{session_id}/debrief", headers=headers)
    assert resp.status_code == 404
```

> Note: the `client` fixture and `db_session` fixture share the same test DB engine (function-scoped), so rows written via `db_session` are visible to the API (both hit `apm_test`). The API's own `get_db` override (in conftest) opens its own session on the same engine.

- [ ] **Step 6: Run** `uv run pytest tests/test_debrief_api.py -v`. Expected: 2 passed.

- [ ] **Step 7: Full gate + commit**
```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest -q
git add backend/app/features/debrief/schemas.py backend/app/features/debrief/router.py backend/app/api/errors.py backend/app/main.py backend/tests/test_debrief_api.py
git commit -m "feat(debrief): API endpoints POST/GET /sessions/{id}/debrief (tested)"
```
Expected: all green.

---

## Self-Review notes (coverage check)

- **Bilan « faute → règle → correction »** → Tasks 2 (value objects), 4 (analyzer), 7 (API).
- **Dans la langue maternelle** → analyzer prompt uses `native_language` (Task 4), fed from `user.native_language` (Task 6).
- **Sortie JSON stricte + anti-hallucination** → Task 3 (robust parse) + Task 4 (span-grounding drop).
- **Estimation CEFR** → Task 4 (validated against `VALID_CEFR`, fallback).
- **Persistance / lecture** → Task 5 (model+repo), 7 (endpoints).
- **DeepSeek derrière l'interface, fake en test** → reuses `app/features/conversation` `LlmProvider` + `build_llm_provider`; `DEBRIEF_ENGINE=fake` default.

**Deliberately deferred (follow-up issue):** ERRANT-based canonical error typing (heavy spaCy dep) — the span-grounding guard already provides the core anti-hallucination protection. **Fluency metrics (CrisperWhisper)** need audio, not just the text transcript — belongs with the audio pipeline (sub-project 2 task 9 / a later task), not here. The `elicitation` pedagogy (asking the learner to self-correct) is a conversation-time behavior already covered by the prompt in sub-project 2; the debrief is the deferred review.
```
