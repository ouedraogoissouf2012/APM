"""Tests for audio transcoding to the format wav2vec2 needs: PCM mono 16 kHz.

The pure validation logic (empty / oversized input) is tested without librosa.
The real decode+resample is exercised with a genuine in-memory WAV (needs
soundfile, which ships with librosa); it is skipped if that stack is absent so
the pure tests still run in a torch-free environment.
"""

import io
import math
import struct
import wave

import pytest

from pronunciation.ml.transcode import TranscodeError, to_pcm_16k_mono


def _wav_bytes(sample_rate: int, seconds: float = 0.1, channels: int = 1) -> bytes:
    """A tiny sine-wave WAV at the given sample rate/channels, 16-bit PCM."""
    n = int(sample_rate * seconds)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n):
            val = int(30000 * math.sin(2 * math.pi * 220 * i / sample_rate))
            for _ in range(channels):
                frames += struct.pack("<h", val)
        w.writeframes(bytes(frames))
    return buf.getvalue()


def test_rejects_empty_audio():
    with pytest.raises(TranscodeError):
        to_pcm_16k_mono(b"")


def test_rejects_oversized_audio():
    with pytest.raises(TranscodeError):
        to_pcm_16k_mono(b"x" * 10, max_bytes=5)


def _has_audio_stack() -> bool:
    import importlib.util

    return importlib.util.find_spec("soundfile") is not None


@pytest.mark.skipif(not _has_audio_stack(), reason="soundfile/librosa not installed")
def test_resamples_44100_to_16000_mono():
    samples = to_pcm_16k_mono(_wav_bytes(44100, seconds=0.1))
    # 0.1 s at 16 kHz -> ~1600 samples (allow a small resampler tolerance).
    assert 1500 <= len(samples) <= 1700
    assert all(-1.0 <= s <= 1.0 for s in samples[:50])  # normalized float


@pytest.mark.skipif(not _has_audio_stack(), reason="soundfile/librosa not installed")
def test_downmixes_stereo_to_mono():
    samples = to_pcm_16k_mono(_wav_bytes(16000, seconds=0.1, channels=2))
    assert 1500 <= len(samples) <= 1700  # already 16 kHz, stereo -> mono
