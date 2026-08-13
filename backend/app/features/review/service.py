"""Review (SRS) business logic: turns each session's errors into a per-error-type
spaced-repetition schedule, and lists what is due to review.

Applies the pure scheduler (`on_error_seen` / `on_error_absent`) to every error
type the learner already tracks PLUS any new type seen this session. `now` is
injected so the whole flow is deterministically testable.
"""

from datetime import datetime

from app.core.pagination import resolve_limit
from app.features.review.models import ReviewItem
from app.features.review.repository import ReviewRepository
from app.features.review.scheduler import (
    ReviewState,
    on_error_absent,
    on_error_seen,
)


class ReviewService:
    def __init__(self, repo: ReviewRepository) -> None:
        self._repo = repo

    async def record_session(
        self,
        user_id: int,
        errors_seen: dict[str, str],
        now: datetime,
    ) -> None:
        """Update the SRS schedule from one session's errors.

        `errors_seen` maps error_type -> its latest correction this session. Every
        tracked type not present is treated as a clean session (streak grows); every
        present type is (re)scheduled at J+1. New types start their ladder.
        """
        # Serialise concurrent record_session calls for the SAME learner (#361,
        # mirrors #302): without this, two concurrent calls (e.g. two devices
        # each finishing a different session around the same time) could both
        # read the same pre-update schedule below and race to write the next
        # SRS stage, silently losing an advance. See ReviewRepository.lock_for_user.
        await self._repo.lock_for_user(user_id)
        existing = {item.error_type: item for item in await self._repo.list_for_user(user_id)}

        # Types to process: everything already tracked + everything seen now. Each
        # upsert only stages its change; a single commit at the end makes the whole
        # session's schedule advance atomically (rolled back together on failure, so
        # the shared request session is left clean for the rest of the debrief flow).
        all_types = set(existing) | set(errors_seen)
        try:
            for error_type in all_types:
                if not error_type.strip():
                    continue
                item = existing.get(error_type)
                state = _to_state(item)
                if error_type in errors_seen:
                    new_state = on_error_seen(state, errors_seen[error_type], now)
                else:
                    new_state = on_error_absent(state, now)
                await self._repo.upsert(
                    user_id,
                    error_type,
                    stage=new_state.stage,
                    clean_streak=new_state.clean_streak,
                    status=new_state.status,
                    next_review_at=new_state.next_review_at,
                    latest_correction=new_state.latest_correction,
                )
            await self._repo.commit()
        except Exception:
            await self._repo.rollback()
            raise

    async def list_due(
        self, user_id: int, now: datetime, *, limit: int | None = None
    ) -> list[ReviewItem]:
        # Naturally bounded by the error-type taxonomy, but cap it anyway so the
        # endpoint can never issue an unbounded query (#233).
        return await self._repo.list_due(user_id, now, limit=resolve_limit(limit))


def _to_state(item: ReviewItem | None) -> ReviewState:
    if item is None:
        return ReviewState()
    return ReviewState(
        stage=item.stage,
        clean_streak=item.clean_streak,
        status=item.status,
        next_review_at=item.next_review_at,
        latest_correction=item.latest_correction,
    )
