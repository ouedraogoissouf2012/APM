"""Convert target English text to the sequence of expected IPA phonemes, so the
GOP scorer knows what the learner was SUPPOSED to say.

Uses the `phonemizer` package (espeak backend), imported lazily. Splitting the
phonemized string into individual phoneme symbols is pure and unit-testable.
"""


class PhonemizeError(Exception):
    """The text could not be phonemized (e.g. espeak backend unavailable)."""


def split_phonemes(phonemized: str) -> list[str]:
    """Split a phonemizer output string into individual phoneme symbols.

    phonemizer (with a phone separator) yields tokens like "θ ɪ ŋ k" per word,
    words separated by whitespace. We flatten to a flat phoneme list. Pure — no
    backend needed, so it is unit-tested directly.
    """
    return [p for p in phonemized.replace("\n", " ").split(" ") if p]


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

    # A space between phonemes; word/syllable separators must DIFFER from it when
    # non-empty (phonemizer rejects equal separators), so we leave them empty —
    # split_phonemes flattens across words anyway.
    return Separator(phone=" ", word="", syllable="")
