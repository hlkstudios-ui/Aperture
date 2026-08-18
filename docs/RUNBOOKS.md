# Production Incident Runbooks

These procedures assume an incident commander, a second operator for verification, access through audited production roles, and correlation through `X-Request-ID`. Preserve evidence before changing state. Never paste secrets, session cookies, signed URLs, customer questions, or media keys into tickets or chat.

## Host access or capacity failure

Trigger: Hostinger availability event, failed host audit, disk-free threshold breach, clock
drift, Docker daemon failure, unexpected public port, or inability to establish approved SSH.

1. Freeze deployments, uploads, processing retries, migrations, firewall edits, and host
   reboots. Preserve the VPS event timeline and out-of-band console access.
2. Run the read-only Hostinger host audit from the console or an existing approved session.
   Never weaken SSH or publish database, Redis, MinIO console, or ClamAV ports to regain access.
3. For disk pressure, stop new uploads/processing and identify bounded Docker logs, derived
   media, database growth, or unexpected files. Do not delete database files, MinIO objects,
   volumes, or unverified backups manually.
4. For compromise indicators or an unapproved port/firewall rule, isolate at the Hostinger
   managed firewall, preserve evidence, rotate credentials from a clean device, and rebuild
   from verified images plus tested backups rather than trusting in-place cleanup.
5. Restore only after time synchronization, SSH policy, firewall, Docker policy, capacity,
   readiness, off-site backup/replica freshness, public smoke, and one complete alert window
   pass. Record any provider encryption/host evidence without secrets.

## Failed media processing

Trigger: `ApertureProcessingFailures`, a failed job in Studio Operations, or a customer title losing a Ready source.

1. Identify the job ID, asset ID, stage, attempt, deployment version, and correlated worker log/error event.
2. Confirm storage and queue health before retrying. Inspect the bounded worker error and source metadata; do not download licensed media to an unmanaged device.
3. If the source is invalid, quarantine the asset and return it to the authorized uploader with the exact supported-format failure. If infrastructure failed, correct that dependency first.
4. Retry once through Studio. Confirm probing → processing → validating → Ready, manifest validation, and a private entitled playback check.
5. If the retry fails, stop retries, preserve input/output prefixes, escalate to media engineering, and keep the title unavailable rather than assigning partial output.

## DB unavailable

Trigger: `/ready` returns 503 with `database=error`, database connection alerts, or sustained API failures.

1. Declare the incident and freeze deployments, migrations, publishing, billing writes, and manual failover.
2. Check provider health, connection saturation, primary/replica role, disk, locks, and the last migration using read-only control-plane access.
3. Restore connectivity or perform the documented provider failover. Never create an empty replacement database or run downgrade during an outage.
4. Verify migration head, `SELECT 1`, `/ready`, authentication, catalog reads, and one reversible non-customer write in staging-equivalent diagnostics.
5. Reopen writes gradually, monitor error/latency rates, and reconcile queued jobs and external webhooks by idempotency key.

## Storage unavailable

Trigger: `ApertureStorageUnavailable`, `/ready` reports `object_storage=error`, uploads fail, or manifests/segments return errors.

1. Stop upload completion and processing retries; keep authorization intact and do not redirect clients to raw storage.
2. Check provider status, bucket existence, endpoint/DNS/TLS, IAM policy, quota, and KMS status without printing credentials.
3. Restore the existing bucket/versioned data path. Do not recreate missing objects from database keys or make the bucket public.
4. Verify a server-side bucket HEAD, one authorized private object read, signed upload to a disposable key, checksum completion, and cleanup.
5. Confirm `/ready`, storage metrics, upload, processing, and playback before resolving.

## Queue backlog

Trigger: `ApertureMediaQueueBacklog`, `ApertureQueuedJobStale`, or increasing queue age.

1. Compare Redis queue length with queued database jobs and inspect worker heartbeat/process supervision and recent deploys.
2. Determine whether throughput is constrained by CPU, storage, database, a poison job, or missing workers.
3. Scale only within tested concurrency and storage/CPU limits. Never delete queue entries to improve the graph.
4. For a poison job, stop the consumer safely, preserve its ID, mark it through the supported failure path, and resume FIFO processing.
5. Confirm backlog and oldest age fall, Ready/failed terminal states reconcile, and no queued database job was stranded after claim.

## CDN/origin issue

Trigger: `AperturePlaybackOriginErrors`, elevated buffering, segment 4xx/5xx, or regional playback complaints.

1. Segment by region, ISP, rendition, player version, source, and request ID; distinguish entitlement 401/403 from origin/CDN failure.
2. Check DNS/TLS, cache status, origin health, range requests, manifest/segment content types, token expiry, and clock skew.
3. Preserve private authorization. Never bypass the API/CDN token boundary or expose object-store URLs as a workaround.
4. Purge only confirmed corrupt cache keys, drain a bad origin, or roll back the responsible delivery configuration.
5. Verify first frame, rendition switching, range delivery, buffering, and fatal-error rate from at least two regions before closing.

## Admin lockout

Trigger: the single administrator cannot authenticate, loses MFA, or is disabled.

1. Verify identity through the organization’s out-of-band incident process; never accept an email or chat-only reset request.
2. Check API/readiness, rate limits, time synchronization, administrator active state, session expiry, and audit history.
3. Use an unused recovery code when valid. Otherwise run the interactive server-side provisioning/rotation command from an audited production shell with dual control.
4. Rotate the password, re-enroll MFA, revoke all previous administrator sessions/recovery codes, and inspect audit events for compromise.
5. Confirm Studio access and record the recovery without storing credentials or TOTP secrets.

## Bad deployment

Trigger: failed rollout health, elevated 5xx/latency, missing metrics, schema mismatch, or a critical regression after release.

1. Halt the rollout and identify application, worker, configuration, and migration versions plus the first failing request ID.
2. Compare health/readiness, logs, error tracking, metrics, and smoke tests against the last healthy version.
3. If code/config is backward-compatible, roll traffic back using the deployment platform. Do not reverse a data migration until its tested downgrade and data-loss behavior are explicitly approved.
4. If rollback is unsafe, disable the affected feature at the approved boundary, keep protected data fail-closed, and roll forward with a reviewed fix.
5. Run health/readiness, auth, catalog, upload, processing, playback, Studio, and monitoring smoke checks; watch one full alert window before resolving.
