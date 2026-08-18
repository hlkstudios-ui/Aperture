FROM python:3.12.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system aperture \
    && useradd --system --gid aperture --home-dir /app aperture
WORKDIR /app
COPY apps/api/pyproject.toml apps/api/requirements.lock ./
COPY apps/api/app ./app
COPY apps/api/migrations ./migrations
COPY apps/api/alembic.ini ./
COPY apps/api/scripts ./scripts
RUN pip install --no-cache-dir --requirement requirements.lock
USER aperture
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
