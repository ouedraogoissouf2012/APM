"""Best-effort Discord/Slack webhook for 5xx and meter_failures (#502)."""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from app.config import get_settings

_logger = logging.getLogger(__name__)
_last_sent: dict[str, float] = {}
_COOLDOWN_SECONDS = 60.0


def notify(event: str, text: str) -> None:
    url = get_settings().alert_webhook_url.strip()
    if not url:
        return
    now = time.monotonic()
    if now - _last_sent.get(event, 0) < _COOLDOWN_SECONDS:
        return
    _last_sent[event] = now
    try:
        asyncio.get_running_loop().create_task(_post(url, text))
    except RuntimeError:
        return


async def _post(url: str, text: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, json={"content": text, "text": text})
    except httpx.HTTPError:
        _logger.warning("alert webhook failed", exc_info=True)


def reset_for_tests() -> None:
    _last_sent.clear()
