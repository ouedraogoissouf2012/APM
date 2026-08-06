"""Unit tests for PostDebriefEnrichment (#188 / ADR 0001).

Every enrichment is best-effort and ISOLATED: one failing must never stop the
debrief nor the other enrichments.
"""

from datetime import UTC, datetime

import pytest

from app.features.debrief.domain import DebriefError, DebriefResult, VocabularyWord
from app.features.debrief.enrichment import PostDebriefEnrichment

NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


class _Vocab:
    def __init__(self, fail=False):
        self.calls: list = []
        self._fail = fail

    async def capture(self, user_id, session_id, words):
        if self._fail:
            raise RuntimeError("vocab down")
        self.calls.append((user_id, session_id, [w.word for w in words]))


class _Review:
    def __init__(self, fail=False):
        self.calls: list = []
        self._fail = fail

    async def record_session(self, user_id, errors_seen, now):
        if self._fail:
            raise RuntimeError("review down")
        self.calls.append((user_id, errors_seen, now))


class _Analytics:
    def __init__(self, fail=False):
        self.calls: list = []
        self._fail = fail

    async def session_completed(self, user_id, session_id, cefr, error_count):
        if self._fail:
            raise RuntimeError("analytics down")
        self.calls.append((user_id, session_id, cefr, error_count))


def _result():
    return DebriefResult(
        cefr_estimate="B1",
        summary="ok",
        errors=[DebriefError(original="i go", correction="I went", rule="r", error_type="tense")],
        words=[VocabularyWord(word="deployment", translation="déploiement")],
    )


def _enrichment(vocab, review, analytics):
    return PostDebriefEnrichment(
        vocabulary=vocab, review=review, analytics=analytics, now=lambda: NOW
    )


@pytest.mark.asyncio
async def test_all_enrichments_run_on_success():
    vocab, review, analytics = _Vocab(), _Review(), _Analytics()
    await _enrichment(vocab, review, analytics).run(
        7, 1, _result(), errors=[{"error_type": "tense"}]
    )

    assert vocab.calls == [(7, 1, ["deployment"])]
    assert review.calls == [(7, {"tense": "I went"}, NOW)]
    assert analytics.calls == [(7, 1, "B1", 1)]


@pytest.mark.asyncio
async def test_a_vocab_failure_does_not_stop_review_or_analytics():
    vocab, review, analytics = _Vocab(fail=True), _Review(), _Analytics()
    await _enrichment(vocab, review, analytics).run(
        7, 1, _result(), errors=[{"error_type": "tense"}]
    )

    assert vocab.calls == []  # it failed
    assert len(review.calls) == 1  # but the rest still ran
    assert len(analytics.calls) == 1


@pytest.mark.asyncio
async def test_a_review_failure_does_not_stop_analytics():
    vocab, review, analytics = _Vocab(), _Review(fail=True), _Analytics()
    await _enrichment(vocab, review, analytics).run(
        7, 1, _result(), errors=[{"error_type": "tense"}]
    )

    assert len(vocab.calls) == 1
    assert review.calls == []
    assert len(analytics.calls) == 1


@pytest.mark.asyncio
async def test_an_analytics_failure_is_swallowed():
    vocab, review, analytics = _Vocab(), _Review(), _Analytics(fail=True)
    # Must not raise — the debrief already succeeded.
    await _enrichment(vocab, review, analytics).run(
        7, 1, _result(), errors=[{"error_type": "tense"}]
    )

    assert len(vocab.calls) == 1
    assert len(review.calls) == 1


@pytest.mark.asyncio
async def test_review_runs_even_with_no_errors():
    # An error-free session still grows the clean streak of tracked types (#117).
    review = _Review()
    result = DebriefResult(cefr_estimate="B1", summary="clean", errors=[], words=[])
    await _enrichment(_Vocab(), review, _Analytics()).run(7, 1, result, errors=[])

    assert review.calls == [(7, {}, NOW)]
