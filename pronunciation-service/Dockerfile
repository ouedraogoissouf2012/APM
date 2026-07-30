# Pronunciation scoring microservice (phoneme-level GOP via wav2vec2).
# Heavy by design (torch + model ~2-3 GB) — isolated here so the main APM
# backend image stays small.
FROM python:3.12-slim

# System deps: espeak-ng (phonemizer backend) + libsndfile/ffmpeg (librosa decode).
RUN apt-get update && apt-get install -y --no-install-recommends \
    espeak-ng \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# uv for reproducible installs (same tool as the main backend).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
# Install core + the `ml` extra (torch CPU + transformers + librosa + phonemizer).
# torch from the CPU index keeps the image smaller; the rest from PyPI. Single
# source of truth for versions = pyproject/uv.lock (no duplicated dep list).
ENV UV_TORCH_BACKEND=cpu
RUN uv pip install --system ".[ml]"

COPY src ./src
ENV PYTHONPATH=/app/src

# Pre-download the model at build time so the first request is fast and the
# container has no runtime network dependency for weights.
ARG MODEL_ID=facebook/wav2vec2-xlsr-53-espeak-cv-ft
RUN python -c "from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor; \
    Wav2Vec2Processor.from_pretrained('${MODEL_ID}'); \
    Wav2Vec2ForCTC.from_pretrained('${MODEL_ID}')"

EXPOSE 8100
CMD ["uvicorn", "pronunciation.main:app", "--host", "0.0.0.0", "--port", "8100"]
