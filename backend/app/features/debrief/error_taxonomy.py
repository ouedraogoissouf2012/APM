"""Canonical debrief error categories.

This lightweight taxonomy gives the MVP stable categories without adding the
heavy ERRANT/spaCy runtime to CI. A future ERRANT adapter can replace the
normalizer while keeping the public `error_type` contract stable.
"""

from __future__ import annotations

import re

CANONICAL_ERROR_TYPES = {
    "grammar",
    "verb_tense",
    "verb_form",
    "subject_verb_agreement",
    "word_order",
    "article",
    "preposition",
    "pronoun",
    "plural",
    "spelling",
    "punctuation",
    "capitalization",
    "vocabulary",
    "word_choice",
    "fluency",
    "other",
}

_ALIASES = {
    "agreement": "subject_verb_agreement",
    "subject verb agreement": "subject_verb_agreement",
    "subject-verb agreement": "subject_verb_agreement",
    "sva": "subject_verb_agreement",
    "tense": "verb_tense",
    "verb tense": "verb_tense",
    "past tense": "verb_tense",
    "verb": "verb_form",
    "verb form": "verb_form",
    "word order": "word_order",
    "syntax": "word_order",
    "articles": "article",
    "determiner": "article",
    "prepositions": "preposition",
    "pronouns": "pronoun",
    "singular plural": "plural",
    "singular/plural": "plural",
    "capital i": "capitalization",
    "capitalisation": "capitalization",
    "vocab": "vocabulary",
    "lexical": "vocabulary",
    "word choice": "word_choice",
    "wrong word": "word_choice",
}

_NON_WORD = re.compile(r"[^a-z0-9]+")


def normalize_error_type(value: str) -> str:
    normalized = _NON_WORD.sub(" ", value.lower()).strip()
    normalized = _ALIASES.get(normalized, normalized.replace(" ", "_"))
    if normalized in CANONICAL_ERROR_TYPES:
        return normalized
    return "other"
