FROM python:3.12.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system aperture \
    && useradd --system --gid aperture --home-dir /app aperture
WORKDIR /app
COPY apps/api/pyproject.toml ./
COPY apps/api/app ./app
COPY apps/api/migrations ./migrations
COPY apps/api/alembic.ini ./
COPY apps/api/scripts ./scripts
COPY deploy/staging/free-tier/start_api.py ./start_api.py
RUN pip install --no-cache-dir .
USER aperture
EXPOSE 10000
CMD ["python", "start_api.py"]
