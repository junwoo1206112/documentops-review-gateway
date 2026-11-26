FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DOCUMENTS_DB_PATH=/app/data/documentops.db

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY fixtures ./fixtures
COPY scripts ./scripts

RUN pip install --no-cache-dir . \
    && python -m app.evaluate --dataset fixtures/evaluation \
         --report artifacts/evaluation_report.json \
    && python -m app.evaluate --dataset fixtures/evaluation_layout2 \
         --report artifacts/evaluation_report_evaluation_layout2.json \
    && adduser --disabled-password --gecos "" --uid 10001 appuser \
    && mkdir -p /app/data /app/artifacts \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"

CMD ["sh", "-c", "uvicorn app.asgi:app --host 0.0.0.0 --port ${PORT:-8000}"]
