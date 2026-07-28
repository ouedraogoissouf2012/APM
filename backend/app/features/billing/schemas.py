from pydantic import BaseModel

from app.features.billing.domain import SettableTier


class SubscriptionOut(BaseModel):
    tier: str
    is_premium: bool
    free_daily_minutes: int
    minutes_used_today: float
    # float('inf') for premium; serialized by the router into a JSON-safe form.
    remaining_minutes: float | None

    model_config = {"from_attributes": True}


class SetTierIn(BaseModel):
    """Admin request to change a user's tier. Literal-validated: an unknown tier
    is rejected with 422 before reaching the service."""

    tier: SettableTier
