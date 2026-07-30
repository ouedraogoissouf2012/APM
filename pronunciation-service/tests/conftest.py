"""Shared, reusable test doubles.

`FakeModel` is the single substitutable implementation of the
`PhonemeAcousticModel` Protocol used across unit AND integration tests — no torch,
no weights. Defining it once here (instead of copy-pasting into each test module)
is the DRY, LSP-honouring way to exercise the pipeline: any test injects it in
place of the real wav2vec2 model.
"""

import math

import pytest


class FakeModel:
    """A tiny deterministic phoneme model over 3 symbols: blank/'a'/'b'.

    It "hears" a scripted phoneme at each frame (`per_frame`), emitting a high
    log-prob for it and a low one for the others — enough to drive the CTC
    alignment + GOP scoring without any real acoustic model.
    """

    _VOCAB = {"<pad>": 0, "a": 1, "b": 2}

    def __init__(self, per_frame: list[str]) -> None:
        self._per_frame = per_frame

    @property
    def blank_id(self) -> int:
        return self._VOCAB["<pad>"]

    def phoneme_to_id(self, phoneme: str) -> int | None:
        return self._VOCAB.get(phoneme)

    def id_to_phoneme(self) -> dict[int, str]:
        return {i: p for p, i in self._VOCAB.items()}

    def emission_log_probs(self, samples: list[float]) -> list[list[float]]:
        rows = []
        for heard in self._per_frame:
            probs = dict.fromkeys(self._VOCAB, 0.1)
            probs[heard] = 0.9
            rows.append([math.log(probs[k]) for k in self._VOCAB])
        return rows


@pytest.fixture
def make_fake_model():
    """Factory fixture: `make_fake_model(["a", "a", "b"])` -> a FakeModel.

    A factory (not a plain instance) because each test scripts a different
    per-frame sequence.
    """
    return FakeModel
