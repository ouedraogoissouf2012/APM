"""#354: the async engine's connection pool must be explicitly sized (not left
at SQLAlchemy's implicit default), with pre_ping/recycle enabled. Asserts
against the actual module-level `engine` singleton the app serves requests
with, not a freshly constructed test double.
"""

from app.config import get_settings
from app.database import engine


def test_engine_pool_is_explicitly_configured_from_settings():
    settings = get_settings()
    pool = engine.pool

    assert pool.size() == settings.db_pool_size
    assert pool._max_overflow == settings.db_max_overflow
    assert pool._pre_ping is True
    assert pool._recycle == settings.db_pool_recycle_seconds
