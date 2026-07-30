# APM — Pronunciation Scoring Microservice

Phoneme-level pronunciation scoring for *Anglais Pour Moi*, using the open-source
**wav2vec2** phoneme model and **Goodness of Pronunciation (GOP)** — no Azure, no
paid API. Given a target sentence and the learner's audio, it returns a score in
`[0, 1]` for **each expected phoneme**.

## Why a separate service?

The ML stack (torch + transformers + the ~1 GB acoustic model) makes the image
~2–3 GB. Isolating it here keeps the main APM backend small and independently
deployable/scalable — the backend calls this service over HTTP only when phoneme
scoring is requested. This was a deliberate, user-validated architectural choice.

## How scoring works

1. **Transcode** the uploaded audio to 16 kHz mono float32 (`ml/transcode.py`, librosa).
2. **Phonemize** the target text into expected IPA phonemes (`ml/phonemize.py`, espeak).
3. **Emit** per-frame log-probabilities over the phoneme alphabet with wav2vec2
   (`ml/model.py`).
4. **Align** each expected phoneme to its frames via **CTC forced alignment**
   (`ml/gop.py`, pure-Python Viterbi — no deprecated `torchaudio.forced_align`).
5. **Score** each phoneme as its mean softmax-posterior over the aligned frames,
   normalized against all competing phonemes (Witt & Young style GOP).

## Architecture (layered, SOLID/DIP)

```
api/        HTTP only — routes, request/response schemas
services/   orchestration — ScoringService wires the pipeline
ml/         the ML core — model, transcode, phonemize, gop (alignment + score)
core/       config (pydantic-settings)
```

The scoring core depends on a `PhonemeAcousticModel` **Protocol**, not on torch.
Tests inject a tiny fake model, so the scientific logic (CTC alignment + GOP) is
fully unit-tested **without loading any weights**. `ml/gop.py` takes plain nested
lists — it has no torch import at all.

## Run

### Docker (production artifact)

From the repo root:

```bash
docker compose --profile ml up --build pronunciation
```

The image installs espeak-ng/ffmpeg/libsndfile, the CPU ML stack, and pre-downloads
the model at build time. Health: `GET http://localhost:8100/health`.

### Local (development)

```bash
uv sync                       # dev deps (ruff, mypy, pytest)
# Full ML stack for the e2e / audio tests (heavy):
uv pip install --python .venv "torch>=2.5" --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .venv "transformers>=4.46" "librosa>=0.10" soundfile "phonemizer>=3.3"
# espeak-ng must be installed system-wide (Windows: winget install eSpeak-NG.eSpeak-NG).
```

Quality gate (all must be green):

```bash
uv run --no-project ruff check src tests scripts
uv run --no-project ruff format --check src tests scripts
uv run --no-project mypy src
uv run --no-project pytest -q        # pure-logic tests (no ML stack needed)
.venv/Scripts/python -m pytest -q    # full suite incl. audio (ML stack needed)
```

Real end-to-end against the actual model:

```bash
PHONEMIZER_ESPEAK_LIBRARY="/c/Program Files/eSpeak NG/libespeak-ng.dll" \
  .venv/Scripts/python scripts/e2e_real_model.py     # synthesizes "think", prints GOP
```

## API

`POST /score` — multipart: `audio` (file) + `target_text` (form field).
Returns `{ "phonemes": [ { "phoneme", "score", "start", "end" }, ... ] }`.

## Calibration

The score is a **calibrated GOP** (Witt & Young): per frame, `log P(target) −
log P(best competitor)`, averaged over the aligned frames, then mapped to `[0,1]`
by a logistic centered from measured behaviour (`ml/gop.py::_gop_to_score`). This
matters because the multilingual model splits probability mass between confusable
phonemes: a correctly-pronounced `/θ/` in "think" emits a raw posterior of only
~0.08 (it "leaks" to `/f/`), yet its GOP (~−2.1) is clearly separable from a truly
wrong one — saying "sink" scores GOP ~−4.8. After calibration these read **0.79
(good) vs 0.06 (needs practice)** — the same sound, correctly discriminated.

## Tracked debt (honest limitations)

- **The logistic is calibrated on the model's own behaviour, not yet on a corpus
  of real French-speaker recordings.** The `/θ/`-vs-`/f/` boundary was measured, but
  a full per-phoneme reference table (many phonemes, many speakers) would make the
  bands more reliable across all sounds. The UI still shows the score **with an
  uncertainty note**, never as an absolute verdict.
- Running this locally means **two services** (backend + this one) — added infra
  complexity, accepted for the deployment/scaling isolation it buys.
