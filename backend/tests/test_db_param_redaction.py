"""DB errors must not leak learner data into logs.

Two layers, both relevant to the domain-5xx logging (#402):

1. ``hide_parameters=True`` on the engine keeps SQLAlchemy's bound parameters
   (e.g. the argon2 password hash) out of the exception string that the catch-all
   ``_unhandled_exception_handler`` logs with ``exc_info``.
2. The DataError/IntegrityError handlers log WITHOUT ``exc_info``, because the
   driver's DETAIL for a unique violation contains the CONFLICTING VALUE (e.g. the
   email) — which ``hide_parameters`` does NOT hide.
"""

import logging

import pytest
from sqlalchemy.exc import IntegrityError

from app.api.errors import _log_db_constraint_error
from app.features.auth.models import User


@pytest.mark.asyncio
async def test_bound_parameters_are_hidden_in_db_error_strings(db_session):
    # The argon2 hash rides in the INSERT's bound parameters. With hide_parameters
    # the engine renders a placeholder instead of the parameter values.
    secret_hash = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdHNhbHQ$c2VjcmV0aGFzaHZhbA"
    db_session.add(User(email="dup@example.com", hashed_password=secret_hash, native_language="fr"))
    await db_session.flush()
    db_session.add(User(email="dup@example.com", hashed_password=secret_hash, native_language="fr"))
    with pytest.raises(IntegrityError) as excinfo:
        await db_session.flush()

    rendered = str(excinfo.value)
    assert "hidden due to hide_parameters" in rendered
    assert secret_hash not in rendered


def test_db_constraint_handler_logs_without_the_conflicting_value(caplog):
    # A SQLAlchemy DB error's str() carries the driver DETAIL, which for a unique
    # violation includes the conflicting value. The handler must log value-free.
    leaked = "victim@example.com"
    exc = ValueError(
        "duplicate key value violates unique constraint\n"
        f"DETAIL: Key (email)=({leaked}) already exists."
    )

    class _Req:
        method = "POST"
        url = type("_Url", (), {"path": "/auth/register"})()
        scope = {"apm_request_id": "req-42"}

    with caplog.at_level(logging.WARNING):
        _log_db_constraint_error(_Req(), exc)

    # No exc_info was passed, so str(exc) (and its DETAIL) never reaches the log.
    assert leaked not in caplog.text
    # It still logs enough to spot the surprise.
    assert "/auth/register" in caplog.text
    assert "ValueError" in caplog.text
