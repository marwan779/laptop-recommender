FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download and cache jinaai/jina-embeddings-v3 (Variant B: float32, 512d Matryoshka) during image build
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('jinaai/jina-embeddings-v3', trust_remote_code=True, truncate_dim=512)"

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

COPY . .

# Ensure ./chroma_reviews_db is baked in; build if missing from context
RUN if [ ! -d "./chroma_reviews_db" ]; then python chroma_reviews_engine.py; fi

EXPOSE 8000

CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
