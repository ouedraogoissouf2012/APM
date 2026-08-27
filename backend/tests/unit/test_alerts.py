import asyncio
from types import SimpleNamespace

import pytest

from app.core import alerts


@pytest.fixture(autouse=True)
def _reset():
    alerts.reset_for_tests()
    yield
    alerts.reset_for_tests()


@pytest.mark.asyncio
async def test_notify_is_noop_when_webhook_unset(monkeypatch):
    posted: list[str] = []

    async def fake_post(url: str, text: str) -> None:
        posted.append(text)

    monkeypatch.setattr(alerts, "_post", fake_post)
    monkeypatch.setattr(
        alerts, "get_settings", lambda: SimpleNamespace(alert_webhook_url="")
    )
    alerts.notify("5xx", "boom")
    await asyncio.sleep(0)
    assert posted == []


@pytest.mark.asyncio
async def test_notify_posts_once_then_cools_down(monkeypatch):
    posted: list[str] = []

    async def fake_post(url: str, text: str) -> None:
        posted.append(text)

    monkeypatch.setattr(alerts, "_post", fake_post)
    monkeypatch.setattr(
        alerts,
        "get_settings",
        lambda: SimpleNamespace(alert_webhook_url="https://hooks.example/x"),
    )
    alerts.notify("5xx", "first")
    alerts.notify("5xx", "second")
    await asyncio.sleep(0)
    assert posted == ["first"]
