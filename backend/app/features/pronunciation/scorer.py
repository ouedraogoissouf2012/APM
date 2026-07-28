"""Word-level pronunciation scoring from a Whisper verbose transcript.

Pure and deterministic. For each target word we find the matching heard word
(same normalization/consume-once rule as the shadowing diff) and turn it into a
clarity score.

Honest about the signal: Whisper (via Groq) `verbose_json` returns per-word
`{word, start, end}` but NO per-word probability — verified against the real API.
So the score today is BINARY presence, not a continuous phonetic measure:

- a word Whisper heard  -> score 1.0 (it came through clearly),
- a word Whisper missed -> score 0.0 (it did not),
- both with `confidence` so the UI shows them.

If a provider DOES supply a per-word probability (a future GOP/wav2vec2 engine),
the scorer uses it as a continuous score instead — the interface already carries
it (`TranscriptWord.probability`), so that engine plugs in without changing this
contract. Continuous phonetic quality is issue #111 step 2.
"""

import re

from app.features.conversation.providers.interfaces import VerboseTranscript
from app.features.pronunciation.domain import WordScore

_WORD = re.compile(r"[a-z0-9']+")

# Confidence attached to a presence-based verdict (heard=1 / missed=0). Not 1.0:
# "the recognizer heard it" is strong but not proof of perfect pronunciation.
_PRESENCE_CONFIDENCE = 0.7


def _normalize(word: str) -> str:
    return "".join(_WORD.findall(word.lower()))


def score_words(target: str, verbose: VerboseTranscript) -> list[WordScore]:
    # No per-word data at all -> we cannot judge any word. Return unknown scores
    # (the UI hides them) instead of claiming every word was missed.
    if not verbose.words:
        return [WordScore(word=raw) for raw in target.split() if _normalize(raw)]

    # Bucket heard words by normalized form, in order, so each is consumed once.
    heard: dict[str, list[float | None]] = {}
    for tw in verbose.words:
        key = _normalize(tw.word)
        if key:
            heard.setdefault(key, []).append(tw.probability)

    scores: list[WordScore] = []
    for raw in target.split():
        key = _normalize(raw)
        if not key:
            continue
        probs = heard.get(key)
        if probs:
            probability = probs.pop(0)
            if probability is not None:
                # A provider that supplies a real probability (e.g. GOP) -> use it
                # as a continuous score.
                scores.append(
                    WordScore(
                        word=raw,
                        score=round(max(0.0, min(1.0, probability)), 3),
                        confidence=_PRESENCE_CONFIDENCE,
                    )
                )
            else:
                # Whisper: no probability -> heard means it came through clearly.
                scores.append(WordScore(word=raw, score=1.0, confidence=_PRESENCE_CONFIDENCE))
        else:
            # Not heard at all: a confident zero.
            scores.append(WordScore(word=raw, score=0.0, confidence=_PRESENCE_CONFIDENCE))
    return scores
