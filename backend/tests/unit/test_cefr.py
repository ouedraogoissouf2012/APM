from app.features.debrief.cefr import next_cefr_level


def test_promotes_one_step_toward_a_higher_estimate():
    # A2, not a jump straight to B1.
    assert next_cefr_level("A1", "B1") == "A2"


def test_demotes_one_step_toward_a_lower_estimate():
    assert next_cefr_level("B2", "A2") == "B1"


def test_stays_when_estimate_equals_current():
    assert next_cefr_level("B1", "B1") == "B1"


def test_never_exceeds_c2():
    assert next_cefr_level("C2", "C2") == "C2"


def test_never_below_a1():
    assert next_cefr_level("A1", "A1") == "A1"


def test_unknown_current_is_treated_as_a1():
    assert next_cefr_level("", "B1") == "A2"


def test_unknown_estimate_leaves_the_level_unchanged():
    assert next_cefr_level("B1", "ZZ") == "B1"
