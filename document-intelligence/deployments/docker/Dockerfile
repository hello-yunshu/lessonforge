# Production builds MUST pass a digest-pinned image, for example:
# --build-arg PYTHON_BASE_IMAGE=python:3.11.11-slim-bookworm@sha256:<digest>
ARG PYTHON_BASE_IMAGE
FROM ${PYTHON_BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    DI_DEPLOYMENT_PROFILE=production \
    DI_WORKSPACE=/data \
    DI_PARSER_CONFIG=/app/configs/parsers.yaml \
    DI_PDF_RENDER_BACKEND=disabled

WORKDIR /app
COPY requirements/production.txt ./requirements/production.txt
RUN python -m pip install --no-cache-dir -r requirements/production.txt
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src ./src
COPY configs ./configs
RUN python -m pip install --no-cache-dir --no-deps . \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /data /app

USER appuser
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/livez', timeout=3).read()"]
CMD ["uvicorn", "document_intelligence.api.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
