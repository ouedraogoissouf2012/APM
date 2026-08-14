"""Unit tests for auth/router.py's client-IP resolution wiring (#401).

_client_host is the ONLY call site of client_ip() in the whole backend (the
other rate-limited routes migrated to user_rate_limit_key, #356), so a missing
argument here silently makes the corresponding Settings field dead everywhere.
"""

from app.config import get_settings
from app.features.auth.router import _client_host


class _FakeClient:
    def __init__(self, host: str) -> None:
        self.host = host


class _FakeRequest:
    def __init__(self, host: str, headers: dict[str, str]) -> None:
        self.client = _FakeClient(host)
        self.headers = headers


def test_client_host_propagates_configured_trusted_proxy_count(monkeypatch):
    # Two trusted proxies in front (CDN -> LB, both appending): the real client
    # ends up 2nd-from-right in X-Forwarded-For. With trusted_proxy_count stuck
    # at the client_ip() default of 1, this would resolve to the LB's own IP
    # instead of the real client (#401) — collapsing every user behind that LB
    # into one rate-limit bucket.
    settings = get_settings()
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    monkeypatch.setattr(settings, "trusted_proxy_count", 2)
    req = _FakeRequest("10.0.0.1", {"X-Forwarded-For": "1.1.1.1, 203.0.113.9, 198.51.100.1"})

    assert _client_host(req) == "203.0.113.9"


def test_client_host_falls_back_to_socket_peer_when_proxy_untrusted(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "trust_proxy_headers", False)
    monkeypatch.setattr(settings, "trusted_proxy_count", 2)
    req = _FakeRequest("10.0.0.1", {"X-Forwarded-For": "1.1.1.1, 203.0.113.9, 198.51.100.1"})

    assert _client_host(req) == "10.0.0.1"
