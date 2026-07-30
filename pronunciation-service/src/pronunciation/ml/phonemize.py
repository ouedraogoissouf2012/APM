"""Convert target English text to the sequence of expected IPA phonemes, so the
GOP scorer knows what the learner was SUPPOSED to say.

Uses the `phonemizer` package (espeak backend), imported lazily. Splitting the
phonemized string into individual phoneme symbols is pure and unit-testable.
"""


class PhonemizeError(Exception):
    """The text could not be phonemized (e.g. espeak backend unavailable)."""


def split_phonemes(phonemized: str) -> list[str]:
    """Split a phonemizer output string into individual phoneme symbols.

    phonemizer yields phonemes separated by a space and WORDS separated by "|"
    (a distinct marker, required: an empty word separator fuses the last phoneme
    of one word with the first of the next, e.g. "s|ɪ" -> "sɪ", an unknown token
    the model drops — collapsing a whole sentence to a handful of phonemes). We
    flatten to a flat phoneme list, dropping the "|" boundary markers.
    """
    normalized = phonemized.replace("\n", " ").replace("|", " ")
    return [p for p in normalized.split(" ") if p]


def phonemize_text(text: str, language: str = "en-us") -> list[str]:
    """Expected IPA phonemes for `text`. Raises PhonemizeError on backend failure."""
    if not text.strip():
        return []
    from phonemizer import phonemize  # lazy: espeak backend is heavy

    try:
        out = phonemize(
            text,
            language=language,
            backend="espeak",
            separator=_phone_separator(),
            strip=True,
        )
    except Exception as exc:
        raise PhonemizeError("Could not phonemize text") from exc
    return split_phonemes(out if isinstance(out, str) else " ".join(out))


def _phone_separator() -> object:
    # Return type is `object`: phonemizer's Separator ships no stubs, and the only
    # caller passes it straight back to phonemize(). Keeps mypy strict elsewhere.
    from phonemizer.separator import Separator

    # Space between phonemes, "|" between WORDS. The word separator MUST be
    # non-empty and different from the phone separator: an empty one fuses the
    # boundary phonemes ("s|ɪ" -> "sɪ", an unknown token), which silently drops
    # most of a sentence. split_phonemes discards the "|" markers when flattening.
    return Separator(phone=" ", word="|", syllable="")
