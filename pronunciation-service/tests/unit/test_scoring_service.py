"""Unit tests for the scoring service orchestration, with a FAKE acoustic model
(no torch, no weights). Verifies the pipeline wires transcode -> phonemize ->
emission -> GOP, and maps unknown phonemes gracefully."""

import math

from pronunciation.services.scoring_service import ScoringService


class _FakeModel:
    """A tiny deterministic phoneme model over 3 symbols: blank, 'a', 'b'.
    Emits high probability for whichever phoneme the test's samples encode."""

    def __init__(self, per_frame: list[str]) -> None:
        # per_frame is the phoneme the model 'hears' at each frame.
        self._per_frame = per_frame
        self._vocab = {"<pad>": 0, "a": 1, "b": 2}

    @property
    def blank_id(self) -> int:
        return 0

    def phoneme_to_id(self, phoneme: str) -> int | None:
        return self._vocab.get(phoneme)

    def id_to_phoneme(self) -> dict[int, str]:
        return {i: p for p, i in self._vocab.items()}

    def emission_log_probs(self, samples: list[float]) -> list[list[float]]:
        rows = []
        for heard in self._per_frame:
            probs = {"<pad>": 0.1, "a": 0.1, "b": 0.1}
            probs[heard] = 0.9
            rows.append([math.log(probs["<pad>"]), math.log(probs["a"]), math.log(probs["b"])])
        return rows


def _service(model, expected_phonemes: list[str]) -> ScoringService:
    # Inject a phonemizer stub so we don't need espeak: text -> fixed phonemes.
    return ScoringService(model=model, phonemizer=lambda _text, _lang: expected_phonemes)


def test_scores_well_pronounced_phonemes_high():
    # Target "a b"; the model hears exactly a then b -> both should score high.
    model = _FakeModel(["a", "a", "b", "b"])
    result = _service(model, ["a", "b"]).score(samples=[0.0] * 4, target_text="ab")
    by_ph = {s.phoneme: s.score for s in result}
    assert by_ph["a"] > 0.7
    assert by_ph["b"] > 0.7


def test_scores_confused_phoneme_low():
    # Target "a" but the model hears "b" throughout -> low score for "a".
    model = _FakeModel(["b", "b", "b"])
    result = _service(model, ["a"]).score(samples=[0.0] * 3, target_text="a")
    assert result[0].phoneme == "a"
    assert result[0].score < 0.5


def test_unknown_phoneme_is_skipped():
    # The phonemizer returns a phoneme the model's vocab doesn't have -> skipped,
    # never crashes.
    model = _FakeModel(["a", "a"])
    result = _service(model, ["a", "θ"]).score(samples=[0.0] * 2, target_text="x")
    assert [s.phoneme for s in result] == ["a"]  # unknown "θ" dropped


def test_empty_target_yields_no_scores():
    model = _FakeModel(["a"])
    result = _service(model, []).score(samples=[0.0], target_text="")
    assert result == []
