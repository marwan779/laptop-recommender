FROM python:3.13-slim AS builder

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

COPY app ./app


FROM python:3.13-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwrightz

RUN addgroup --gid 10001 app \
    && adduser --uid 10001 --gid 10001 --disabled-password --gecos "" app

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --chown=app:app --from=builder /app/app ./app

RUN patchright install --with-deps chromium \
    && chmod -R 755 /ms-playwright

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
