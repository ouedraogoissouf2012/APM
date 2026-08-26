"""Outbound transactional email (Resend). Off when key/from are empty."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Protocol

import httpx

from app.config import Settings, get_settings
from app.core.http_lifecycle import register_closeable

_logger = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"


class Mailer(Protocol):
    async def send(self, *, to: str, subject: str, text: str) -> None: ...


class NullMailer:
    async def send(self, *, to: str, subject: str, text: str) -> None:
        return None


class ResendMailer:
    def __init__(self, client: httpx.AsyncClient, api_key: str, from_addr: str) -> None:
        self._client = client
        self._api_key = api_key
        self._from = from_addr

    async def send(self, *, to: str, subject: str, text: str) -> None:
        try:
            response = await self._client.post(
                _RESEND_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "from": self._from,
                    "to": [to],
                    "subject": subject,
                    "text": text,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError:
            _logger.warning("mailer send failed", exc_info=True)

    async def aclose(self) -> None:
        await self._client.aclose()


def build_mailer(settings: Settings) -> Mailer:
    if not settings.mailer_enabled:
        return NullMailer()
    client = httpx.AsyncClient(timeout=10.0)
    return register_closeable(
        ResendMailer(client, settings.resend_api_key.strip(), settings.mail_from.strip())
    )


@lru_cache
def shared_mailer() -> Mailer:
    return build_mailer(get_settings())
