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

# uv for reproducible installs (same tool as the main backend). Pin the image
# tag — `:latest` would silently change the resolver across rebuilds (#417).
COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
# Install core + the `ml` extra (torch CPU + transformers + librosa + phonemizer).
# `uv sync --frozen` honours uv.lock (and UV_TORCH_BACKEND=cpu). `uv pip install
# ".[ml]"` would re-resolve and ignore the lock (#417).
ENV UV_TORCH_BACKEND=cpu
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV PATH="/app/.venv/bin:$PATH"
RUN uv sync --frozen --extra ml --no-dev

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
