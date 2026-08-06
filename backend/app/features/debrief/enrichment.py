"""Post-debrief enrichment (ADR 0001).

Best-effort side-effects that ENRICH a debrief but must never break it: vocabulary
capture (#116), spaced-repetition scheduling (#117) and product analytics (#129).
They run only AFTER the authoritative debrief is durable, and each is isolated so a
failure in one is logged and swallowed — never fatal to the debrief the learner
just earned, and never blocking the others.

Extracted out of DebriefService so `generate()` stays pure orchestration and each
effect lives behind its own collaborator (SRP / the audit's god-object finding).
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.features.analytics.service import AnalyticsService
    from app.features.debrief.domain import DebriefResult
    from app.features.review.service import ReviewService
    from app.features.vocabulary.service import VocabularyService

_logger = logging.getLogger(__name__)


class PostDebriefEnrichment:
    def __init__(
        self,
        vocabulary: "VocabularyService | None" = None,
        review: "ReviewService | None" = None,
        analytics: "AnalyticsService | None" = None,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._vocabulary = vocabulary
        self._review = review
        self._analytics = analytics
        self._now = now

    async def run(
        self,
        user_id: int,
        session_id: int,
        result: "DebriefResult",
        errors: list[dict],
    ) -> None:
        """Run every enrichment, each isolated so one failure never stops the rest."""
        await self._capture_vocabulary(user_id, session_id, result)
        await self._schedule_review(user_id, result)
        await self._emit_analytics(user_id, session_id, result, len(errors))

    async def _capture_vocabulary(
        self, user_id: int, session_id: int, result: "DebriefResult"
    ) -> None:
        if self._vocabulary is None or not result.words:
            return
        try:
            await self._vocabulary.capture(user_id, session_id, result.words)
        except Exception:
            _logger.warning("Vocabulary capture failed for session %s", session_id, exc_info=True)

    async def _schedule_review(self, user_id: int, result: "DebriefResult") -> None:
        # Even an error-free session matters — it grows the clean streak of tracked
        # types toward mastery (#117) — so this runs regardless of `errors`.
        if self._review is None:
            return
        try:
            errors_seen: dict[str, str] = {}
            for e in result.errors:
                if e.error_type.strip():
                    errors_seen.setdefault(e.error_type, e.correction)
            await self._review.record_session(user_id, errors_seen, self._now())
        except Exception:
            _logger.warning("Review scheduling failed for user %s", user_id, exc_info=True)

    async def _emit_analytics(
        self, user_id: int, session_id: int, result: "DebriefResult", error_count: int
    ) -> None:
        # AnalyticsService is best-effort internally, but call it defensively too so
        # a bug there can never break the debrief flow.
        if self._analytics is None:
            return
        try:
            await self._analytics.session_completed(
                user_id, session_id, result.cefr_estimate, error_count
            )
        except Exception:
            _logger.warning("Analytics emit failed for session %s", session_id, exc_info=True)
