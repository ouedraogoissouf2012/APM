from fastapi import APIRouter, Depends

from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.progress.dependencies import get_progress_service
from app.features.progress.schemas import (
    CefrPointOut,
    ProgressOut,
    RecurringErrorOut,
)
from app.features.progress.service import ProgressService

router = APIRouter(prefix="/me", tags=["progress"])


@router.get("/progress", response_model=ProgressOut)
async def get_progress(
    current_user: User = Depends(get_current_user),
    service: ProgressService = Depends(get_progress_service),
) -> ProgressOut:
    """The learner's progress: CEFR trend + recurring error types, aggregated
    server-side (replaces the client's one-debrief-per-session fetch loop)."""
    snap = await service.snapshot(current_user.id)
    return ProgressOut(
        cefr_trend=[
            CefrPointOut(session_id=p.session_id, started_at=p.started_at, level=p.level)
            for p in snap.cefr_trend
        ],
        recurring_errors=[
            RecurringErrorOut(
                error_type=e.error_type,
                count=e.count,
                latest_correction=e.latest_correction,
            )
            for e in snap.recurring_errors
        ],
    )
