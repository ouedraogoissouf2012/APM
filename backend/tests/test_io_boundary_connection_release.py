"""#415: sibling endpoints of #399 must not hold a pool connection across external I/O.

get_current_user checks a connection out; these routes then call STT / TTS / LLM
and (for missions/onboarding/transfer) persist afterwards. The proof is the same
as test_conversation_connection_release.py: pool.checkedout() == 0 at the instant
the external provider runs.
"""

import json

import pytest
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm.interfaces import TranscriptWord, VerboseTranscript
from app.database import bind_io_boundary, get_db
from app.features.auth.repository import SqlAlchemyUserRepository
from app.features.conversation.dependencies import get_tts_provider
from app.features.debrief.domain import DebriefResult
from app.features.missions.compiler import MissionCompiler
from app.features.missions.dependencies import get_mission_service
from app.features.missions.repository import SqlAlchemyMissionRepository
from app.features.missions.service import MissionService
from app.features.onboarding.dependencies import get_onboarding_service
from app.features.onboarding.service import OnboardingService
from app.features.profile.repository import SqlAlchemyProfileRepository
from app.features.shadowing.coach import ShadowingCoach
from app.features.shadowing.dependencies import (
    get_shadowing_service,
    get_shadowing_service_with_stt,
)
from app.features.shadowing.generator import PhraseGenerator
from app.features.shadowing.service import ShadowingService
from app.main import app


async def _auth_header(client, email: str) -> dict[str, str]:
    reg = await client.post("/auth/register", json={"email": email, "password": "s3cret!pass"})
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


class _PoolProbingLlm:
    def __init__(self, engine, observed: list[int], payload: str) -> None:
        self._engine = engine
        self._observed = observed
        self._payload = payload

    async def complete(self, system_prompt, history):
        self._observed.append(self._engine.pool.checkedout())
        return self._payload


class _PoolProbingTts:
    def __init__(self, engine, observed: list[int]) -> None:
        self._engine = engine
        self._observed = observed

    async def synthesize(self, text: str) -> bytes:
        self._observed.append(self._engine.pool.checkedout())
        return b"ID3fake-mp3-bytes"


class _PoolProbingStt:
    def __init__(self, engine, observed: list[int]) -> None:
        self._engine = engine
        self._observed = observed

    async def transcribe(self, data: bytes) -> str:
        self._observed.append(self._engine.pool.checkedout())
        return "the ship is sinking"

    async def transcribe_verbose(self, data: bytes) -> VerboseTranscript:
        self._observed.append(self._engine.pool.checkedout())
        return VerboseTranscript(
            text="the ship is sinking",
            words=[TranscriptWord(w, 0.9) for w in ["the", "ship", "is", "sinking"]],
        )


class _PoolProbingAnalyzer:
    def __init__(self, engine, observed: list[int]) -> None:
        self._engine = engine
        self._observed = observed

    async def analyze(self, turns, native_language, fallback_cefr="A1", intensity=None):
        self._observed.append(self._engine.pool.checkedout())
        return DebriefResult(cefr_estimate="B1", summary="", errors=[])


_PHRASE_JSON = json.dumps(
    {"text": "The ship is sinking.", "focus": "ship_sheep", "tip": "short i"}
)
_COACH_JSON = json.dumps({"coaching": "Say ship with a short i."})
_MISSION_JSON = json.dumps(
    {
        "persona": "A friendly interviewer",
        "goal": "Introduce yourself",
        "likely_questions": ["Tell me about yourself."],
    }
)


@pytest.mark.asyncio
async def test_tts_releases_connection_during_synthesis(client, _engine):
    observed: list[int] = []
    app.dependency_overrides[get_tts_provider] = lambda: _PoolProbingTts(_engine, observed)
    try:
        headers = await _auth_header(client, "release-tts@b.com")
        resp = await client.post("/tts", headers=headers, json={"text": "hello"})
        assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.pop(get_tts_provider, None)

    assert observed == [0], f"connection held during TTS (checkedout={observed})"


@pytest.mark.asyncio
async def test_shadowing_phrase_releases_connection_during_llm(client, _engine):
    observed: list[int] = []
    llm = _PoolProbingLlm(_engine, observed, _PHRASE_JSON)
    app.dependency_overrides[get_shadowing_service] = lambda: ShadowingService(
        generator=PhraseGenerator(llm), coach=ShadowingCoach(llm)
    )
    try:
        headers = await _auth_header(client, "release-phrase@b.com")
        resp = await client.post("/shadowing/phrase", headers=headers)
        assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.pop(get_shadowing_service, None)

    assert observed == [0], f"connection held during phrase LLM (checkedout={observed})"


@pytest.mark.asyncio
async def test_shadowing_attempt_releases_connection_during_stt(client, _engine):
    observed: list[int] = []
    app.dependency_overrides[get_shadowing_service_with_stt] = lambda: ShadowingService(
        generator=PhraseGenerator(_PoolProbingLlm(_engine, observed, _PHRASE_JSON)),
        coach=ShadowingCoach(_PoolProbingLlm(_engine, observed, _COACH_JSON)),
        stt=_PoolProbingStt(_engine, observed),
    )
    try:
        headers = await _auth_header(client, "release-attempt@b.com")
        resp = await client.post(
            "/shadowing/attempt",
            headers=headers,
            files={"audio": ("clip.webm", b"not-really-audio", "audio/webm")},
            data={"target_text": "The ship is sinking."},
        )
        assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.pop(get_shadowing_service_with_stt, None)

    assert observed == [0], f"connection held during attempt STT (checkedout={observed})"


@pytest.mark.asyncio
async def test_shadowing_coach_releases_connection_during_llm(client, _engine):
    observed: list[int] = []
    llm = _PoolProbingLlm(_engine, observed, _COACH_JSON)
    app.dependency_overrides[get_shadowing_service] = lambda: ShadowingService(
        generator=PhraseGenerator(llm), coach=ShadowingCoach(llm)
    )
    try:
        headers = await _auth_header(client, "release-coach@b.com")
        resp = await client.post(
            "/shadowing/coach",
            headers=headers,
            json={"target_text": "The ship is sinking.", "missed_words": ["ship"]},
        )
        assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.pop(get_shadowing_service, None)

    assert observed == [0], f"connection held during coach LLM (checkedout={observed})"


def _mission_with_probe(db: AsyncSession, llm) -> MissionService:
    return MissionService(
        missions=SqlAlchemyMissionRepository(db),
        compiler=MissionCompiler(llm),
        io_boundary=bind_io_boundary(db),
    )


@pytest.mark.asyncio
async def test_create_mission_releases_connection_during_compile(client, _engine):
    observed: list[int] = []

    def _override(db: AsyncSession = Depends(get_db)) -> MissionService:
        return _mission_with_probe(db, _PoolProbingLlm(_engine, observed, _MISSION_JSON))

    app.dependency_overrides[get_mission_service] = _override
    try:
        headers = await _auth_header(client, "release-mission@b.com")
        resp = await client.post(
            "/missions",
            headers=headers,
            json={"source_type": "offer", "content": "Backend engineer at Acme"},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["persona"]
    finally:
        app.dependency_overrides.pop(get_mission_service, None)

    assert observed == [0], f"connection held during mission compile (checkedout={observed})"


@pytest.mark.asyncio
async def test_transfer_releases_connection_during_compile(client, _engine):
    observed: list[int] = []

    def _override(db: AsyncSession = Depends(get_db)) -> MissionService:
        return _mission_with_probe(db, _PoolProbingLlm(_engine, observed, _MISSION_JSON))

    app.dependency_overrides[get_mission_service] = _override
    try:
        headers = await _auth_header(client, "release-transfer@b.com")
        resp = await client.post("/me/transfer/job_interview", headers=headers)
        assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.pop(get_mission_service, None)

    assert observed == [0], f"connection held during transfer compile (checkedout={observed})"


@pytest.mark.asyncio
async def test_placement_releases_connection_during_analyzer(client, _engine):
    observed: list[int] = []

    def _override(db: AsyncSession = Depends(get_db)) -> OnboardingService:
        return OnboardingService(
            analyzer=_PoolProbingAnalyzer(_engine, observed),
            profiles=SqlAlchemyProfileRepository(db),
            users=SqlAlchemyUserRepository(db),
            io_boundary=bind_io_boundary(db),
        )

    app.dependency_overrides[get_onboarding_service] = _override
    try:
        headers = await _auth_header(client, "release-place@b.com")
        resp = await client.post(
            "/onboarding/placement",
            headers=headers,
            json={
                "answers": ["I have been learning English for a few years now."],
                "interests": ["travel"],
                "goal": "job interview",
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["cefr_level"] == "B1"
        me = await client.get("/auth/me", headers=headers)
        assert me.json()["cefr_level"] == "B1"
    finally:
        app.dependency_overrides.pop(get_onboarding_service, None)

    assert observed == [0], f"connection held during placement LLM (checkedout={observed})"
