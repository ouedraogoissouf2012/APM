from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from app.features.analytics.aggregate import AnalyticsAggregateService
from app.features.analytics.dependencies import get_analytics_aggregate_service
from app.features.analytics.schemas import AnalyticsSummaryOut
from app.features.auth.dependencies import get_current_admin
from app.features.auth.models import User

router = APIRouter(prefix="/admin/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummaryOut)
async def analytics_summary(
    _admin: User = Depends(get_current_admin),
    service: AnalyticsAggregateService = Depends(get_analytics_aggregate_service),
) -> AnalyticsSummaryOut:
    """Admin-only product funnel for the pilot: activated learners, completions
    (total + this week) and transfer challenges started. No personal content —
    only aggregate counts over the append-only events."""
    summary = await service.summary(datetime.now(UTC))
    return AnalyticsSummaryOut(
        users_activated=summary.users_activated,
        completions_total=summary.completions_total,
        completions_this_week=summary.completions_this_week,
        transfers_started_total=summary.transfers_started_total,
    )
