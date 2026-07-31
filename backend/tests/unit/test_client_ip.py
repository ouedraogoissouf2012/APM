"""Unit tests for client-IP resolution behind a proxy (#120).

Rate limiting is keyed by client IP. Behind a reverse proxy, request.client.host
is the PROXY's IP — so every user shares one bucket and per-IP limiting is
useless. We must read X-Forwarded-For, but ONLY when we trust the proxy: otherwise
a client could forge the header to dodge limits or frame another IP.
"""

from app.api.client_ip import client_ip


class _FakeClient:
    def __init__(self, host: str) -> None:
        self.host = host


class _FakeRequest:
    def __init__(self, host: str | None, headers: dict[str, str] | None = None) -> None:
        self.client = _FakeClient(host) if host is not None else None
        self.headers = headers or {}


def test_uses_socket_ip_when_proxy_is_not_trusted():
    # Untrusted: ignore any client-supplied X-Forwarded-For, use the real peer.
    req = _FakeRequest("10.0.0.1", {"X-Forwarded-For": "1.2.3.4"})
    assert client_ip(req, trust_proxy=False) == "10.0.0.1"


def test_uses_forwarded_for_first_hop_when_proxy_is_trusted():
    # Trusted proxy: the left-most XFF entry is the original client.
    req = _FakeRequest("10.0.0.1", {"X-Forwarded-For": "203.0.113.9, 70.41.3.18, 10.0.0.1"})
    assert client_ip(req, trust_proxy=True) == "203.0.113.9"


def test_trims_whitespace_in_forwarded_for():
    req = _FakeRequest("10.0.0.1", {"X-Forwarded-For": "  203.0.113.9  "})
    assert client_ip(req, trust_proxy=True) == "203.0.113.9"


def test_falls_back_to_socket_ip_when_trusted_but_header_absent():
    req = _FakeRequest("10.0.0.1", {})
    assert client_ip(req, trust_proxy=True) == "10.0.0.1"


def test_falls_back_to_socket_ip_when_forwarded_for_is_blank():
    req = _FakeRequest("10.0.0.1", {"X-Forwarded-For": "   "})
    assert client_ip(req, trust_proxy=True) == "10.0.0.1"


def test_anonymous_when_no_client_and_no_header():
    # No socket peer (e.g. test transport) and no header -> a stable sentinel, not
    # a crash, so limiting still buckets something.
    req = _FakeRequest(None, {})
    assert client_ip(req, trust_proxy=False) == "anonymous"


def test_anonymous_when_no_client_but_trusted_header_present():
    req = _FakeRequest(None, {"X-Forwarded-For": "203.0.113.9"})
    assert client_ip(req, trust_proxy=True) == "203.0.113.9"
