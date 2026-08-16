from app.core import metrics


def test_inc_and_snapshot_and_reset():
    metrics.reset()
    assert metrics.snapshot() == {}
    metrics.inc(metrics.METER_FAILURES)
    metrics.inc(metrics.METER_FAILURES)
    metrics.inc(metrics.PURGE_FAILURES)
    assert metrics.snapshot() == {"meter_failures": 2, "purge_failures": 1}
    metrics.reset()
    assert metrics.snapshot() == {}
