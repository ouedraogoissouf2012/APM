"""Resolve the real client IP, safely, for rate limiting (#120).

Rate limits are keyed by client IP. Behind a reverse proxy, `request.client.host`
is the proxy's address, so every user collapses into one bucket. The proxy passes
the true client in `X-Forwarded-For` — but that header is client-supplied and
trivially forged, so we honour it ONLY when the deployment says a trusted proxy
sits in front (config `trust_proxy_headers`). Otherwise we use the socket peer.
"""

from starlette.requests import Request

_ANONYMOUS = "anonymous"


def client_ip(request: Request, trust_proxy: bool) -> str:
    """The client's IP for rate-limit keying.

    When `trust_proxy` is True, use the left-most `X-Forwarded-For` hop (the
    original client) if present; otherwise fall back to the socket peer. When
    False, always use the socket peer and ignore the (untrusted) header."""
    if trust_proxy:
        forwarded = request.headers.get("X-Forwarded-For", "")
        first_hop = forwarded.split(",")[0].strip()
        if first_hop:
            return first_hop
    peer = request.client.host if request.client else None
    return peer or _ANONYMOUS
