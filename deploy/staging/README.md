# Isolated staging deployment

This topology creates its own PostgreSQL database, Redis persistence, private MinIO bucket, Mailpit inbox, API, media worker, scene worker, production Next.js server, and Caddy HTTPS edge. For now, local development and this isolated staging stack intentionally share the repository-root `.env`; do not reuse that local file for production.

1. Install and start Docker with Compose v2.
2. If the root `.env` does not exist, run `deploy/staging/generate-env.sh` once. It copies the canonical root `.env.example`, replaces local secrets with fresh random values, writes `.env` with mode `0600`, and refuses to overwrite an existing file.
3. The configured `*.127.0.0.1.nip.io` names resolve to loopback without modifying `/etc/hosts`; replace them with controlled staging DNS names for a shared environment.
4. For shared staging, replace the local Caddy `tls internal` policy with an approved publicly trusted certificate and set `ERROR_TRACKING_DSN`.
5. Run `deploy/staging/verify.sh`. It validates Compose, builds immutable images, runs the one-shot migration, starts both workers, verifies HTTPS with Caddy's generated CA, seeds only isolated test metadata, and runs the staging-safe E2E matrix.
6. Run `deploy/staging/restore-test.sh` to create a fresh backup, restore it into a separately named temporary database, and verify migration/table parity. The script drops only its validated `aperture_restore_test_*` database.
7. Run `deploy/staging/verify-feature-flags-off.sh` to rebuild the real staging API/web with every risky feature disabled, verify responsive navigation removal, direct-route and API 404 behavior, screenshots, console errors, failed requests, and server errors in desktop/mobile Chromium, then automatically restore the normal enabled build.

The local verification exposes PostgreSQL, MinIO, and the Mailpit inspection API only on loopback ports for restricted fixture inspection. The application itself uses private service endpoints, while signed browser uploads use `S3_PUBLIC_ENDPOINT` through HTTPS. Mailpit must not be used as a production email service. The isolated media bucket is private and versioned.

`deploy/staging/backup.sh /absolute/restricted/destination` creates a PostgreSQL custom dump, an archive of non-secret deployment configuration, and a checksum manifest. Production must additionally schedule off-site database backups and configure provider-level object replication/durability.

To inspect state from the repository root, use `docker compose --env-file .env -f deploy/staging/compose.yml ps` and the protected Studio Operations page. To stop without deleting evidence, use the same Compose arguments followed by `stop`. Deleting named volumes destroys the isolated staging data and requires explicit operator intent.
