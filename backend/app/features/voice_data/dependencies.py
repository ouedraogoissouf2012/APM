from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.rate_limit import RateLimiter
from app.core.rate_limit_factory import build_rate_limiter
from app.database import get_db
from app.features.voice_data.repository import SqlAlchemyVoiceDataSource, VoiceDataStreamSource
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


def get_voice_data_repository(db: AsyncSession = Depends(get_db)) -> VoiceDataStreamSource:
    """Not the ``VoiceDataService``/Protocol pair used by erasure: the export
    endpoint streams straight from the repository so the response can be
    memory-bounded (#365), which ``VoiceDataService``'s list-returning shape
    can't express without changing it (outside this ticket's territory). Typed
    as ``VoiceDataStreamSource`` (not the concrete class) so the router depends
    on an interface a test can substitute a fake for."""
    return SqlAlchemyVoiceDataSource(db)
