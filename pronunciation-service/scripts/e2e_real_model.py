"""End-to-end check with the REAL wav2vec2 model + espeak (no fakes).

Not part of the pytest suite: it downloads ~1 GB of weights and needs espeak-ng.
Run manually to validate the whole GOP pipeline against a real utterance:

    PHONEMIZER_ESPEAK_LIBRARY="/c/Program Files/eSpeak NG/libespeak-ng.dll" \
        .venv/Scripts/python.exe scripts/e2e_real_model.py path/to/think.wav

If no audio path is given, it synthesizes the word "think" with espeak-ng itself,
so the run is self-contained. Prints the per-phoneme GOP scores.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

# IPA output contains non-cp1252 characters; force UTF-8 so printing on a Windows
# console does not crash the whole run.
sys.stdout.reconfigure(encoding="utf-8")

# Make src importable when run from the repo root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pronunciation.core.config import get_settings  # noqa: E402
from pronunciation.ml.model import Wav2Vec2PhonemeModel  # noqa: E402
from pronunciation.ml.transcode import to_pcm_16k_mono  # noqa: E402
from pronunciation.services.scoring_service import ScoringService  # noqa: E402


def _synth_think_wav() -> bytes:
    """Speak "think" via espeak-ng into a temp WAV, return its bytes."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out = Path(f.name)
    subprocess.run(
        ["espeak-ng", "-v", "en-us", "-w", str(out), "think"],
        check=True,
    )
    data = out.read_bytes()
    out.unlink(missing_ok=True)
    return data


def main() -> int:
    target = "think"
    if len(sys.argv) > 1:
        audio = Path(sys.argv[1]).read_bytes()
        print(f"Using audio file: {sys.argv[1]}")
    else:
        print("No audio given -> synthesizing 'think' with espeak-ng")
        audio = _synth_think_wav()

    settings = get_settings()
    print(f"Loading model {settings.model_id} (first run downloads ~1 GB)...")
    model = Wav2Vec2PhonemeModel(model_id=settings.model_id, device=settings.device)
    service = ScoringService(model=model, language=settings.phonemizer_language)

    samples = to_pcm_16k_mono(audio, max_bytes=settings.max_audio_bytes)
    print(f"Decoded {len(samples)} samples @16kHz mono")

    scores = service.score(samples=samples, target_text=target)
    print(f"\nGOP scores for '{target}':")
    for s in scores:
        bar = "#" * int(s.score * 20)
        print(f"  /{s.phoneme}/  {s.score:.3f}  [{bar:<20}]  frames {s.start}-{s.end}")

    theta = [s for s in scores if s.phoneme in ("θ", "T")]
    if not scores:
        print("\nFAIL: no phoneme scores produced")
        return 1
    print(f"\nOK: {len(scores)} phoneme(s) scored.")
    if theta:
        print(f"θ score = {theta[0].score:.3f} (the /th/ sound French speakers struggle with)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
