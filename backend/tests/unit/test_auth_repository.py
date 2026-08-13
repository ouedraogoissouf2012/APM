"""#357: purge_expired swallows any DB failure (best-effort background purge),
but must log it — otherwise a persistent failure silently lets the
refresh_tokens table grow unbounded again (#239/#271) with no signal.
"""

import logging
from datetime import UTC, datetime

import pytest

from app.features.auth.repository import SqlAlchemyRefreshTokenRepository


class _FailingSession:
    async def execute(self, *args, **kwargs):
        raise RuntimeError("db unavailable")


@pytest.mark.asyncio
async def test_purge_expired_logs_a_warning_on_failure(caplog):
    repo = SqlAlchemyRefreshTokenRepository(_FailingSession())

    with caplog.at_level(logging.WARNING, logger="app.features.auth.repository"):
        result = await repo.purge_expired(datetime.now(UTC))

    assert result == 0
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "WARNING"
    assert caplog.records[0].exc_info is not None
