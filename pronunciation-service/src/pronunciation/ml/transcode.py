"""Transcode arbitrary WAV audio to what wav2vec2 requires: mono, 16 kHz, float32
in [-1, 1]. The browser records WAV at its own sample rate (often 44.1/48 kHz,
possibly stereo), so resampling and down-mixing here is mandatory.

The heavy audio libs (librosa/soundfile) are imported lazily inside the function
so importing this module (e.g. for the pure validation path) never pulls them in.
"""

import io


class TranscodeError(Exception):
    """The audio could not be decoded/resampled."""


_TARGET_SR = 16_000


def to_pcm_16k_mono(audio: bytes, max_bytes: int = 10 * 1024 * 1024) -> list[float]:
    """Decode `audio` (WAV bytes) to a list of mono float samples at 16 kHz.

    Raises TranscodeError on empty, oversized, or undecodable input.
    """
    if not audio:
        raise TranscodeError("Empty audio")
    if len(audio) > max_bytes:
        raise TranscodeError(f"Audio too large ({len(audio)} > {max_bytes} bytes)")

    import librosa  # lazy: keeps the pure validation path torch/librosa-free

    try:
        # sr=16000 resamples; mono=True down-mixes; librosa returns float32 in [-1, 1].
        samples, _ = librosa.load(io.BytesIO(audio), sr=_TARGET_SR, mono=True)
    except Exception as exc:
        raise TranscodeError("Could not decode audio") from exc
    return samples.tolist()
