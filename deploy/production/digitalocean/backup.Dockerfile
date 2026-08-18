FROM postgres:17.10-bookworm

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates python3 python3-venv \
    && python3 -m venv /opt/aperture-backup \
    && /opt/aperture-backup/bin/pip install --no-cache-dir boto3==1.42.54 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY deploy/production/digitalocean/production_backup.py ./production_backup.py
COPY deploy/production/digitalocean/production_restore_verify.py ./production_restore_verify.py
USER postgres
ENTRYPOINT []
CMD ["/opt/aperture-backup/bin/python", "/app/production_backup.py"]
