from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.features.auth.repository import SqlAlchemyUserRepository
from app.features.billing.service import BillingService


def get_billing_service(db: AsyncSession = Depends(get_db)) -> BillingService:
    return BillingService(
        SqlAlchemyUserRepository(db),
        free_daily_minutes=get_settings().free_tier_daily_minutes,
    )
