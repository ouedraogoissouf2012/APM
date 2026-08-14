from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.core.rate_limit import RateLimiter
from app.core.rate_limit_factory import build_rate_limiter
from app.database import get_db
from app.features.voice_data.repository import (
    SqlAlchemyVoiceDataSource,
    VoiceDataExportRepository,
)
from app.features.voice_data.service import VoiceDataService

_settings = get_settings()

# Dedicated limiter for POST /me/voice-data/export (#365): the endpoint streams
# the learner's ENTIRE voice-derived history, so repeated calls are still real
# DB work per request even though the response itself is now memory-bounded.
# Hardcoded rather than settings-driven: config.py is outside this ticket's
# territory in this coordinated wave. 5/hour is generous for the legitimate use
# (a learner reviewing or downloading their own data a couple of times) while
# still capping the "repeatable without throttle" half of the #365 scenario.
_VOICE_DATA_EXPORT_RATE_LIMIT_MAX = 5
_VOICE_DATA_EXPORT_RATE_LIMIT_WINDOW_SECONDS = 3600

_voice_data_export_rate_limiter = build_rate_limiter(
    namespace="voice-data-export",
    max_hits=_VOICE_DATA_EXPORT_RATE_LIMIT_MAX,
    window_seconds=_VOICE_DATA_EXPORT_RATE_LIMIT_WINDOW_SECONDS,
    redis_url=_settings.redis_url,
    max_keys=_settings.rate_limit_max_keys,
)


def get_voice_data_export_rate_limiter() -> RateLimiter:
    return _voice_data_export_rate_limiter


def get_voice_data_service(db: AsyncSession = Depends(get_db)) -> VoiceDataService:
    return VoiceDataService(SqlAlchemyVoiceDataSource(db))


def get_voice_data_export_repository(
    db: AsyncSession = Depends(get_db),
) -> VoiceDataExportRepository:
    """DI seam for the streaming export (#365, #389). The repository is built from
    a fresh sessionmaker bound to the REQUEST ENGINE (``db.bind``), not the request
    session: each keyset page runs in its own short-lived session so the router can
    release the request connection before the client-paced download (see the router's
    ``db.rollback()``). ``db.bind`` is the engine and is unaffected by that rollback.
    Injecting the repo (rather than building it inline) keeps the seam substitutable
    in tests and the router thin."""
    return VoiceDataExportRepository(async_sessionmaker(bind=db.bind, expire_on_commit=False))
