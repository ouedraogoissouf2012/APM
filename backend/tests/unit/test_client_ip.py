"""Unit tests for client-IP resolution behind a proxy (#120, #383).

Rate limiting is keyed by client IP. Behind a reverse proxy, request.client.host
is the PROXY's IP — so every user shares one bucket and per-IP limiting is
useless. We must read X-Forwarded-For, but ONLY when we trust the proxy: otherwise
a client could forge the header to dodge limits or frame another IP.

#383: an APPENDING proxy (nginx's $proxy_add_x_forwarded_for, AWS ALB, GCP LB —
the common case) adds the peer IP it observed at the TCP level to the END of
whatever header arrived, so the real client ends up `trusted_proxy_count`
entries from the RIGHT of the header — everything to its left, INCLUDING the
left-most entry, is attacker-suppliable. The old code took the left-most hop
verbatim, with no IP-format validation: fully attacker-controlled and usable to
mint a fresh rate-limit bucket on every request.
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


def test_uses_forwarded_for_last_hop_when_proxy_is_trusted():
    # A single trusted proxy in front (the default, trusted_proxy_count=1)
    # APPENDS the real client's IP as the last entry — not the first.
    req = _FakeRequest("10.0.0.1", {"X-Forwarded-For": "203.0.113.9, 70.41.3.18, 198.51.100.7"})
    assert client_ip(req, trust_proxy=True) == "198.51.100.7"


def test_left_most_forged_hop_is_ignored_regardless_of_its_value():
    # #383's actual exploit: an attacker sends a DIFFERENT forged left-most
    # value on every request. The result must be IDENTICAL either way — proof
    # the left-most entry has zero influence on the resolved IP (and therefore
    # on any rate-limit key built from it).
    req_a = _FakeRequest("10.0.0.1", {"X-Forwarded-For": "1.1.1.1, 70.41.3.18, 198.51.100.7"})
    req_b = _FakeRequest("10.0.0.1", {"X-Forwarded-For": "9.9.9.9, 70.41.3.18, 198.51.100.7"})
    ip_a = client_ip(req_a, trust_proxy=True)
    ip_b = client_ip(req_b, trust_proxy=True)
    assert ip_a == ip_b == "198.51.100.7"


def test_trims_whitespace_in_forwarded_for():
    req = _FakeRequest("10.0.0.1", {"X-Forwarded-For": "  203.0.113.9  "})
    assert client_ip(req, trust_proxy=True) == "203.0.113.9"


def test_falls_back_to_socket_ip_when_trusted_but_header_absent():
    req = _FakeRequest("10.0.0.1", {})
    assert client_ip(req, trust_proxy=True) == "10.0.0.1"


def test_falls_back_to_socket_ip_when_forwarded_for_is_blank():
    req = _FakeRequest("10.0.0.1", {"X-Forwarded-For": "   "})
    assert client_ip(req, trust_proxy=True) == "10.0.0.1"


def test_falls_back_to_socket_peer_when_the_selected_hop_is_not_a_valid_ip():
    # The chosen hop must be VALIDATED as an IP before use (#383) — a malformed
    # or non-IP token (proxy misconfiguration, or an attacker probing the
    # parser) must never be trusted verbatim as a rate-limit key component.
    req = _FakeRequest("10.0.0.1", {"X-Forwarded-For": "203.0.113.9, not-an-ip"})
    assert client_ip(req, trust_proxy=True) == "10.0.0.1"


def test_falls_back_to_socket_peer_for_a_forged_non_ip_left_most_hop():
    req = _FakeRequest("10.0.0.1", {"X-Forwarded-For": "'; DROP TABLE users;--"})
    assert client_ip(req, trust_proxy=True) == "10.0.0.1"


def test_uses_nth_hop_from_the_right_for_multiple_trusted_proxies():
    # Two trusted proxies in a row (e.g. CDN -> load balancer, both appending):
    # the CDN (closest to the client) appends the real client's IP; the LB then
    # appends the CDN's OWN IP (its immediate peer), landing one entry further
    # right. So for trusted_proxy_count=2, the real client is the 2nd-from-right.
    req = _FakeRequest("10.0.0.1", {"X-Forwarded-For": "1.1.1.1, 203.0.113.9, 198.51.100.1"})
    assert client_ip(req, trust_proxy=True, trusted_proxy_count=2) == "203.0.113.9"


def test_falls_back_to_socket_peer_when_fewer_hops_than_trusted_proxy_count():
    # A misconfiguration (or an attacker sending a truncated header) must not
    # crash or silently pick the wrong entry — fall back to the socket peer.
    req = _FakeRequest("10.0.0.1", {"X-Forwarded-For": "203.0.113.9"})
    assert client_ip(req, trust_proxy=True, trusted_proxy_count=2) == "10.0.0.1"


def test_trusted_proxy_count_of_zero_never_trusts_the_header():
    # Guards a real Python footgun: list[-0] == list[0] (negative zero is zero),
    # so a naive `hops[-trusted_proxy_count]` with trusted_proxy_count=0 would
    # silently pick the LEFT-MOST (attacker-controlled) hop again — reopening
    # #383 for anyone who sets TRUSTED_PROXY_COUNT=0.
    req = _FakeRequest("10.0.0.1", {"X-Forwarded-For": "1.1.1.1, 198.51.100.7"})
    assert client_ip(req, trust_proxy=True, trusted_proxy_count=0) == "10.0.0.1"


def test_trusted_proxy_count_negative_never_trusts_the_header():
    req = _FakeRequest("10.0.0.1", {"X-Forwarded-For": "1.1.1.1, 198.51.100.7"})
    assert client_ip(req, trust_proxy=True, trusted_proxy_count=-1) == "10.0.0.1"


def test_anonymous_when_no_client_and_no_header():
    # No socket peer (e.g. test transport) and no header -> a stable sentinel, not
    # a crash, so limiting still buckets something.
    req = _FakeRequest(None, {})
    assert client_ip(req, trust_proxy=False) == "anonymous"


def test_anonymous_when_no_client_but_trusted_header_present():
    req = _FakeRequest(None, {"X-Forwarded-For": "203.0.113.9"})
    assert client_ip(req, trust_proxy=True) == "203.0.113.9"


def test_ipv6_hop_is_accepted():
    req = _FakeRequest("10.0.0.1", {"X-Forwarded-For": "2001:db8::1, ::ffff:198.51.100.7"})
    assert client_ip(req, trust_proxy=True) == "::ffff:198.51.100.7"
