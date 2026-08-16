import pytest

from app.features.purge.task import try_acquire_purge_lock


@pytest.mark.asyncio
async def test_empty_redis_url_always_acquires():
    assert await try_acquire_purge_lock("", 3600) is True


@pytest.mark.asyncio
async def test_unreachable_redis_skips_the_tick():
    assert await try_acquire_purge_lock("redis://127.0.0.1:1/0", 3600) is False
