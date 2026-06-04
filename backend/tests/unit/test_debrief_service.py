import pytest

from app.domain.exceptions import NotFoundError
from app.features.auth.models import User
from app.features.debrief.analyzer import DebriefAnalyzer
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
            session_id,
            cefr_estimate,
            summary,
            errors,
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
    service = _service(
        owner_id=7, turns=[{"role": "user", "content": "i is happy"}], debriefs=debriefs
    )
    result = await service.generate(session_id=1, user=_user())
    assert result.cefr_estimate == "B1"
    assert debriefs.saved is not None


@pytest.mark.asyncio
async def test_generate_rejects_session_not_owned_by_user():
    service = _service(
        owner_id=999, turns=[{"role": "user", "content": "x"}], debriefs=_FakeDebriefs()
    )
    with pytest.raises(NotFoundError):
        await service.generate(session_id=1, user=_user())


@pytest.mark.asyncio
async def test_generate_rejects_when_no_transcript():
    service = _service(owner_id=7, turns=None, debriefs=_FakeDebriefs())
    with pytest.raises(NotFoundError):
        await service.generate(session_id=1, user=_user())
