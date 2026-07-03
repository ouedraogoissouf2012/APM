from app.features.debrief.error_taxonomy import normalize_error_type


def test_normalize_error_type_keeps_canonical_values():
    assert normalize_error_type("verb_tense") == "verb_tense"
    assert normalize_error_type("spelling") == "spelling"


def test_normalize_error_type_maps_common_aliases():
    assert normalize_error_type("Subject-verb agreement") == "subject_verb_agreement"
    assert normalize_error_type("past tense") == "verb_tense"
    assert normalize_error_type("word choice") == "word_choice"
    assert normalize_error_type("capital i") == "capitalization"


def test_normalize_error_type_falls_back_to_other():
    assert normalize_error_type("strange bespoke label") == "other"
    assert normalize_error_type("") == "other"
