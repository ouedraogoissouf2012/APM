"""Integration tests for POST /score, using a FAKE model injected via dependency
override (no torch, no weights) and a stub phonemizer. Exercises the real HTTP
path: multipart upload, transcode boundary, service, serialization."""

import io
import math
import struct
import wave

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.conftest import FakeModel

from pronunciation.api.routes import router
from pronunciation.core.concurrency import InferenceGate
from pronunciation.dependencies import get_inference_gate, get_scoring_service
from pronunciation.services.scoring_service import ScoringService


def _wav_16k_mono(seconds: float = 0.1) -> bytes:
    sr = 16_000
    n = int(sr * seconds)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(
            b"".join(
                struct.pack("<h", int(20000 * math.sin(2 * math.pi * 220 * i / sr)))
                for i in range(n)
            )
        )
    return buf.getvalue()


def _client(per_frame: list[str], phonemes: list[str]) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    service = ScoringService(model=FakeModel(per_frame), phonemizer=lambda _t, _l: phonemes)
    app.dependency_overrides[get_scoring_service] = lambda: service
    # The route runs scoring through the gate; a real gate works fine in tests and
    # exercises the actual gated code path (off-loop + serialised).
    app.dependency_overrides[get_inference_gate] = lambda: InferenceGate(max_concurrent=1)
    return TestClient(app)


def _has_audio_stack() -> bool:
    import importlib.util

    return importlib.util.find_spec("soundfile") is not None


def test_health():
    app = FastAPI()
    app.include_router(router)
    assert TestClient(app).get("/health").json() == {"status": "ok"}


@pytest.mark.skipif(not _has_audio_stack(), reason="soundfile/librosa not installed")
def test_score_returns_phoneme_scores():
    client = _client(per_frame=["a", "a", "b", "b"], phonemes=["a", "b"])
    resp = client.post(
        "/score",
        data={"target_text": "ab"},
        files={"audio": ("speech.wav", _wav_16k_mono(), "audio/wav")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [p["phoneme"] for p in body["phonemes"]] == ["a", "b"]
    assert all(0.0 <= p["score"] <= 1.0 for p in body["phonemes"])


@pytest.mark.skipif(not _has_audio_stack(), reason="soundfile/librosa not installed")
def test_score_rejects_empty_audio():
    client = _client(per_frame=["a"], phonemes=["a"])
    resp = client.post(
        "/score",
        data={"target_text": "a"},
        files={"audio": ("speech.wav", b"", "audio/wav")},
    )
    assert resp.status_code == 422


def test_score_rejects_oversized_upload_with_413(monkeypatch):
    # #424: cap is enforced while reading, not after buffering the whole body.
    from pronunciation.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("MAX_AUDIO_BYTES", "16")
    try:
        client = _client(per_frame=["a"], phonemes=["a"])
        resp = client.post(
            "/score",
            data={"target_text": "a"},
            files={"audio": ("speech.wav", b"x" * 64, "audio/wav")},
        )
        assert resp.status_code == 413, resp.text
    finally:
        get_settings.cache_clear()
