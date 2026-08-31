FROM python:3.12.14-alpine3.23@sha256:31a768b01976652c222e318fe5bd6e7c252f056cbf489c88fa256f1bf0af58e3

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apk add --no-cache \
        ca-certificates=20260611-r0 \
        libcrypto3=3.5.8-r0 \
        libssl3=3.5.8-r0 \
        sqlite-libs=3.53.4-r0 \
        postgresql17-client=17.11-r0 \
    && addgroup -S -g 10001 aperture-backup \
    && adduser -S -D -H -u 10001 -G aperture-backup aperture-backup \
    && python -m venv /opt/aperture-backup \
    && /opt/aperture-backup/bin/python -m pip install \
        --no-cache-dir --no-compile boto3==1.42.54

WORKDIR /app
# These scripts are provider-neutral despite their legacy directory name. They use only
# PostgreSQL and S3-compatible APIs and are retained there to avoid duplicating audited code.
COPY --chmod=0444 deploy/production/digitalocean/production_backup.py ./production_backup.py
COPY --chmod=0444 deploy/production/digitalocean/production_restore_verify.py ./production_restore_verify.py
USER 10001:10001
ENTRYPOINT []
CMD ["/opt/aperture-backup/bin/python", "/app/production_backup.py"]
