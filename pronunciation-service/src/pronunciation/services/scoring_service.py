"""Orchestrates phoneme-level pronunciation scoring.

Pipeline: target text -> expected phonemes (phonemizer) -> model vocab ids ->
emission log-probs (acoustic model) -> GOP per phoneme (pure aligner). The
acoustic model and the phonemizer are injected (DIP), so the whole service is
unit-tested with a fake model and a stub phonemizer — no torch, no espeak.

Transcoding bytes -> 16 kHz mono samples happens at the API boundary, so this
service works on samples and stays independent of audio decoding.
"""

from collections.abc import Callable

from pronunciation.ml.domain import PhonemeScore
from pronunciation.ml.gop import gop_scores
from pronunciation.ml.model import PhonemeAcousticModel
from pronunciation.ml.phonemize import phonemize_text

# text, language -> list of expected IPA phonemes. Defaults to the real espeak
# phonemizer; tests inject a stub.
Phonemizer = Callable[[str, str], list[str]]


class ScoringService:
    def __init__(
        self,
        model: PhonemeAcousticModel,
        phonemizer: Phonemizer = phonemize_text,
        language: str = "en-us",
    ) -> None:
        self._model = model
        self._phonemizer = phonemizer
        self._language = language

    def score(self, samples: list[float], target_text: str) -> list[PhonemeScore]:
        expected = self._phonemizer(target_text, self._language)
        if not expected:
            return []

        # Map expected phonemes to the model's vocabulary; drop those the model
        # doesn't know (rare, but never crash the request over one symbol).
        target_ids: list[int] = []
        for phoneme in expected:
            pid = self._model.phoneme_to_id(phoneme)
            if pid is not None:
                target_ids.append(pid)
        if not target_ids:
            return []

        log_probs = self._model.emission_log_probs(samples)
        return gop_scores(
            log_probs,
            target_ids,
            self._model.id_to_phoneme(),
            blank=self._model.blank_id,
        )
