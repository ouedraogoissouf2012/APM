from app.features.debrief.domain import VALID_CEFR, DebriefError, DebriefResult


def test_debrief_error_holds_fields():
    e = DebriefError(
        original="I go yesterday",
        correction="I went yesterday",
        rule="Past simple",
        error_type="verb_tense",
    )
    assert e.original == "I go yesterday"
    assert e.correction == "I went yesterday"


def test_debrief_result_defaults_to_empty_errors():
    r = DebriefResult(cefr_estimate="B1", summary="ok")
    assert r.errors == []


def test_valid_cefr_set():
    assert {"A1", "A2", "B1", "B2", "C1", "C2"} == VALID_CEFR
