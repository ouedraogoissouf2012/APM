"""Tests for the pure phoneme-splitting logic (no espeak backend needed)."""

import importlib.util

import pytest

from pronunciation.ml.phonemize import _phone_separator, phonemize_text, split_phonemes

_HAS_PHONEMIZER = importlib.util.find_spec("phonemizer") is not None


def test_splits_space_separated_phonemes():
    assert split_phonemes("θ ɪ ŋ k") == ["θ", "ɪ", "ŋ", "k"]


def test_flattens_multiple_words():
    assert split_phonemes("ð ə  ʃ ɪ p") == ["ð", "ə", "ʃ", "ɪ", "p"]


def test_word_boundary_marker_does_not_fuse_phonemes():
    # Regression (real bug): with word separator "|", the phonemes at word
    # boundaries must stay separate, not fuse (e.g. "s|ɪ" was becoming "sɪ", an
    # unknown token the model dropped, so a whole sentence collapsed to a few
    # phonemes). The "|" is a boundary marker, dropped like whitespace.
    assert split_phonemes("ð ɪ s | ɪ z | m aɪ | h aʊ s") == [
        "ð",
        "ɪ",
        "s",
        "ɪ",
        "z",
        "m",
        "aɪ",
        "h",
        "aʊ",
        "s",
    ]


def test_ignores_empty_tokens_and_newlines():
    assert split_phonemes("  θ \n ɪ  ") == ["θ", "ɪ"]


def test_empty_text_yields_no_phonemes():
    # Empty input short-circuits before touching the espeak backend.
    assert phonemize_text("   ") == []


@pytest.mark.skipif(not _HAS_PHONEMIZER, reason="phonemizer not installed")
def test_separator_is_valid_for_phonemizer():
    # Regression: phonemizer's Separator rejects equal non-empty separators.
    # An earlier phone=" ", word=" " config raised ValueError only at runtime.
    # Constructing it must not raise, and phone must be a single space.
    sep = _phone_separator()
    assert sep.phone == " "
