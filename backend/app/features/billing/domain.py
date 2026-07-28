"""Pure domain types for billing — no I/O, no framework.

A subscription is, for now, just the user's tier and the quota that tier grants.
Payment (Stripe), trials and webhooks are a later slice of the billing epic (#7);
this layer stays independent of any payment provider so that slice can plug in
without touching the tier/quota logic.
"""

from dataclasses import dataclass
from typing import Literal

# The tiers a caller may set. Kept in sync with app.features.auth.models
# (TIER_FREE / TIER_PREMIUM); Literal-validated so a typo is rejected at the edge.
SettableTier = Literal["free", "premium"]


@dataclass(frozen=True)
class Subscription:
    """A snapshot of what the user's tier grants them right now."""

    tier: str
    is_premium: bool
    free_daily_minutes: int
    minutes_used_today: float
    remaining_minutes: float  # float('inf') for premium
