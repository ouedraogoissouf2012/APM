"""Resolve the real client IP, safely, for rate limiting (#120, #383).

Rate limits are keyed by client IP. Behind a reverse proxy, `request.client.host`
is the proxy's address, so every user collapses into one bucket. The proxy passes
the true client in `X-Forwarded-For` — but that header is client-supplied and
trivially forged, so we honour it ONLY when the deployment says a trusted proxy
sits in front (config `trust_proxy_headers`). Otherwise we use the socket peer.
"""

import ipaddress

from starlette.requests import Request

_ANONYMOUS = "anonymous"


def client_ip(request: Request, trust_proxy: bool, trusted_proxy_count: int = 1) -> str:
    """The client's IP for rate-limit keying.

    When `trust_proxy` is True, use the `X-Forwarded-For` hop the trusted proxy
    chain itself appended (#383) — NOT the left-most one. An appending proxy
    (nginx's `$proxy_add_x_forwarded_for`, AWS ALB, GCP LB — the common case)
    adds the peer IP it observed at the TCP level to the END of whatever header
    arrived, so for `trusted_proxy_count` trusted hops in a row the real client
    ends up that many entries from the RIGHT. Everything to its left — including
    the left-most entry, which the old code trusted verbatim — is
    attacker-suppliable: an attacker sitting in front of the first trusted proxy
    can prepend anything before it ever reaches the proxy that appends the real
    IP. The selected entry is validated as an actual IP address before use; a
    missing/blank header, fewer hops than `trusted_proxy_count`, a malformed
    entry, or a nonsensical (<1) `trusted_proxy_count` all fall back to the
    socket peer rather than trust unvalidated input."""
    if trust_proxy and trusted_proxy_count >= 1:
        forwarded = request.headers.get("X-Forwarded-For", "")
        hops = [hop.strip() for hop in forwarded.split(",")] if forwarded.strip() else []
        if len(hops) >= trusted_proxy_count:
            candidate = hops[-trusted_proxy_count]
            if _is_ip_address(candidate):
                return candidate
    peer = request.client.host if request.client else None
    return peer or _ANONYMOUS


def _is_ip_address(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True
