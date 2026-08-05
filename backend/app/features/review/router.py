from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.review.dependencies import get_review_service
from app.features.review.schemas import ReviewItemOut
from app.features.review.service import ReviewService

router = APIRouter(prefix="/me", tags=["review"])


@router.get("/review", response_model=list[ReviewItemOut])
async def list_due_reviews(
    current_user: User = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
) -> list[ReviewItemOut]:
    """The recurring error types due to review now (spaced repetition), soonest
    first. Mastered and not-yet-due types are excluded."""
    items = await service.list_due(current_user.id, datetime.now(UTC))
    return [ReviewItemOut.model_validate(i) for i in items]
