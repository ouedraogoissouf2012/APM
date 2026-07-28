from math import isinf

from fastapi import APIRouter, Depends

from app.features.auth.dependencies import get_current_admin, get_current_user
from app.features.auth.models import User
from app.features.billing.dependencies import get_billing_service
from app.features.billing.domain import Subscription
from app.features.billing.schemas import SetTierIn, SubscriptionOut
from app.features.billing.service import BillingService

router = APIRouter(tags=["billing"])


def _to_out(sub: Subscription) -> SubscriptionOut:
    # inf is not valid JSON; expose "unlimited" as null remaining_minutes.
    remaining = None if isinf(sub.remaining_minutes) else sub.remaining_minutes
    return SubscriptionOut(
        tier=sub.tier,
        is_premium=sub.is_premium,
        free_daily_minutes=sub.free_daily_minutes,
        minutes_used_today=sub.minutes_used_today,
        remaining_minutes=remaining,
    )


@router.get("/me/subscription", response_model=SubscriptionOut)
async def get_my_subscription(
    current_user: User = Depends(get_current_user),
    service: BillingService = Depends(get_billing_service),
) -> SubscriptionOut:
    return _to_out(service.subscription_of(current_user))


@router.post("/admin/users/{user_id}/tier", response_model=SubscriptionOut)
async def set_user_tier(
    user_id: int,
    payload: SetTierIn,
    _admin: User = Depends(get_current_admin),
    service: BillingService = Depends(get_billing_service),
) -> SubscriptionOut:
    """Admin-only: change a user's tier (free/premium). This is how a learner is
    upgraded today; a future Stripe webhook will call the same service."""
    user = await service.set_tier(user_id, payload.tier)
    return _to_out(service.subscription_of(user))
