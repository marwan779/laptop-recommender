FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefix=/install -r requirements.txt

COPY app ./app


FROM python:3.12-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN addgroup --gid 10001 app \
    && adduser --uid 10001 --gid 10001 --disabled-password --gecos "" app

WORKDIR /app

COPY --from=builder /install /usr/local

# Install Chromium before copying app code so Python edits never re-download the browser binary
RUN patchright install --with-deps chromium \
    && chmod -R 755 /ms-playwright \
    && mkdir -p "/app/scraping results" /app/quarantine

COPY --chown=app:app --from=builder /app/app ./app

RUN chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
