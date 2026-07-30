"""Unit tests for the scoring service orchestration, with a FAKE acoustic model
(no torch, no weights). Verifies the pipeline wires transcode -> phonemize ->
emission -> GOP, and maps unknown phonemes gracefully.

The fake model comes from the shared `FakeModel` in tests/conftest.py — one reusable
double for every test, injected in place of wav2vec2 (DIP/LSP)."""

from tests.conftest import FakeModel

from pronunciation.services.scoring_service import ScoringService


def _service(model, expected_phonemes: list[str]) -> ScoringService:
    # Inject a phonemizer stub so we don't need espeak: text -> fixed phonemes.
    return ScoringService(model=model, phonemizer=lambda _text, _lang: expected_phonemes)


def test_scores_well_pronounced_phonemes_high():
    # Target "a b"; the model hears exactly a then b -> both should score high.
    model = FakeModel(["a", "a", "b", "b"])
    result = _service(model, ["a", "b"]).score(samples=[0.0] * 4, target_text="ab")
    by_ph = {s.phoneme: s.score for s in result}
    assert by_ph["a"] > 0.7
    assert by_ph["b"] > 0.7


def test_scores_confused_phoneme_low():
    # Target "a" but the model hears "b" throughout -> low score for "a".
    model = FakeModel(["b", "b", "b"])
    result = _service(model, ["a"]).score(samples=[0.0] * 3, target_text="a")
    assert result[0].phoneme == "a"
    assert result[0].score < 0.5


def test_unknown_phoneme_is_skipped():
    # The phonemizer returns a phoneme the model's vocab doesn't have -> skipped,
    # never crashes.
    model = FakeModel(["a", "a"])
    result = _service(model, ["a", "θ"]).score(samples=[0.0] * 2, target_text="x")
    assert [s.phoneme for s in result] == ["a"]  # unknown "θ" dropped


def test_empty_target_yields_no_scores():
    model = FakeModel(["a"])
    result = _service(model, []).score(samples=[0.0], target_text="")
    assert result == []
