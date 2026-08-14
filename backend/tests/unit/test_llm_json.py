"""#366: app/core/llm_json.py centralises parse_json_object/clip, previously
byte-for-byte duplicated as `_loads`/`_clip` in 5 feature modules. Mirrors and
extends test_debrief_parsing.py's coverage (that module keeps its own
raise-on-failure `parse_debrief_json`, layered on the same extraction idiom;
it is untouched here) with the None-returning cases the 5 duplicates actually
relied on, plus the non-dict-JSON guard and `clip`.
"""

from app.core.llm_json import clip, parse_json_object


def test_parses_plain_json():
    data = parse_json_object('{"has_error": true, "original": "i go"}')
    assert data == {"has_error": True, "original": "i go"}


def test_parses_json_wrapped_in_markdown_fences():
    raw = '```json\n{"coaching": "Try again"}\n```'
    assert parse_json_object(raw) == {"coaching": "Try again"}


def test_parses_json_with_surrounding_prose():
    raw = 'Here is the analysis: {"persona": "a recruiter"} Thanks!'
    assert parse_json_object(raw) == {"persona": "a recruiter"}


def test_returns_none_when_no_braces_are_present():
    assert parse_json_object("sorry, I cannot help with that") is None


def test_returns_none_on_invalid_json_between_the_braces():
    assert parse_json_object("{not valid json}") is None


def test_returns_none_when_the_closing_brace_precedes_the_opening_one():
    # rfind("}") < find("{") — a malformed/reversed fragment, not just absent.
    assert parse_json_object("} some text {") is None


def test_returns_none_for_a_syntactically_valid_but_non_dict_top_level_value():
    # #238: a JSON array or bare scalar parses fine but must not be handed to
    # callers expecting dict.get(...) — every duplicate guarded this the same
    # way; a missed guard in any one copy was the actual bug risk (#366).
    assert parse_json_object("[1, 2, 3]") is None
    assert parse_json_object('"just a string"') is None
    assert parse_json_object("42") is None


def test_extracts_the_outermost_braces_even_with_nested_objects():
    raw = '{"outer": {"inner": true}}'
    assert parse_json_object(raw) == {"outer": {"inner": True}}


def test_clip_strips_whitespace_and_bounds_length():
    assert clip("  hello  ", 10) == "hello"
    assert clip("a" * 500, 400) == "a" * 400


def test_clip_of_a_short_string_is_unchanged_but_stripped():
    assert clip("  short  ", 400) == "short"
