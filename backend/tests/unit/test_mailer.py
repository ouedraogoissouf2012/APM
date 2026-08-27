import httpx
import pytest

from app.features.auth.mailer import NullMailer, ResendMailer, build_mailer


class _FakeSettings:
    def __init__(self, *, key: str = "", from_addr: str = "") -> None:
        self.resend_api_key = key
        self.mail_from = from_addr

    @property
    def mailer_enabled(self) -> bool:
        return bool(self.resend_api_key.strip() and self.mail_from.strip())


@pytest.mark.asyncio
async def test_null_mailer_is_a_noop():
    await NullMailer().send(to="a@b.com", subject="s", text="t")


@pytest.mark.asyncio
async def test_resend_mailer_posts_the_email():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = request.content
        return httpx.Response(200, json={"id": "ok"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    mailer = ResendMailer(client, api_key="re_test", from_addr="APM <n@x.com>")
    await mailer.send(to="a@b.com", subject="Hello", text="body")
    await client.aclose()

    assert seen["url"] == "https://api.resend.com/emails"
    assert seen["auth"] == "Bearer re_test"
    assert b"a@b.com" in seen["body"]  # type: ignore[operator]
    assert b"Hello" in seen["body"]  # type: ignore[operator]


@pytest.mark.asyncio
async def test_resend_mailer_swallows_http_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "nope"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    mailer = ResendMailer(client, api_key="re_bad", from_addr="n@x.com")
    await mailer.send(to="a@b.com", subject="s", text="t")
    await client.aclose()


def test_build_mailer_is_null_when_disabled():
    assert isinstance(build_mailer(_FakeSettings()), NullMailer)  # type: ignore[arg-type]
