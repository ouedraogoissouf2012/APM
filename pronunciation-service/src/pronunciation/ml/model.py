"""The acoustic model behind an interface, so the scoring service depends on an
abstraction (DIP) — a fake replaces it in tests without loading ~1 GB of weights.

`PhonemeAcousticModel` exposes exactly what the GOP scorer needs: turn audio
samples into per-frame emission log-probs, plus the phoneme<->id vocabulary and
the CTC blank id. The real implementation wraps wav2vec2 (torch/transformers),
imported lazily and loaded once.
"""

from typing import Protocol


class PhonemeAcousticModel(Protocol):
    """A CTC phoneme model: audio -> per-frame log-probs over a phoneme alphabet."""

    @property
    def blank_id(self) -> int: ...

    def phoneme_to_id(self, phoneme: str) -> int | None:
        """Vocabulary id for an IPA phoneme, or None if the model doesn't know it."""
        ...

    def id_to_phoneme(self) -> dict[int, str]:
        """Full id->phoneme map (for labelling aligned frames)."""
        ...

    def emission_log_probs(self, samples: list[float]) -> list[list[float]]:
        """Per-frame log-probs (frames x alphabet) for mono-16k float samples."""
        ...


class Wav2Vec2PhonemeModel:
    """Real model: facebook/wav2vec2-xlsr-53-espeak-cv-ft. torch/transformers are
    imported lazily in __init__ so this module is importable without them, and the
    weights load exactly once (the service builds a single instance at startup)."""

    def __init__(self, model_id: str, device: str = "cpu") -> None:
        import torch
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

        self._torch = torch
        self._processor = Wav2Vec2Processor.from_pretrained(model_id)
        # Split the fluent chain: transformers' stubs mistype `.to(...).eval()` on
        # the from_pretrained result, so we keep each step on its own.
        model = Wav2Vec2ForCTC.from_pretrained(model_id)
        # transformers 5.x mistypes nn.Module.to's decorated wrapper (it expects a
        # PreTrainedModel, but `.to("cpu")` with a device string is the real API).
        model.to(device)  # type: ignore[arg-type]
        model.eval()
        self._model = model
        self._device = device
        # Build the id<->phoneme vocabulary from the tokenizer.
        vocab: dict[str, int] = self._processor.tokenizer.get_vocab()
        self._id_to_phoneme = {i: p for p, i in vocab.items()}
        self._phoneme_to_id = vocab
        self._blank_id = self._model.config.pad_token_id or 0

    @property
    def blank_id(self) -> int:
        return self._blank_id

    def phoneme_to_id(self, phoneme: str) -> int | None:
        return self._phoneme_to_id.get(phoneme)

    def id_to_phoneme(self) -> dict[int, str]:
        return dict(self._id_to_phoneme)

    def emission_log_probs(self, samples: list[float]) -> list[list[float]]:
        torch = self._torch
        inputs = self._processor(
            samples, sampling_rate=16_000, return_tensors="pt"
        ).input_values.to(self._device)
        with torch.no_grad():
            logits = self._model(inputs).logits[0]  # (frames, alphabet)
            log_probs = torch.log_softmax(logits, dim=-1)
        return log_probs.cpu().tolist()
