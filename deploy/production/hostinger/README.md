# Hostinger VPS production target

This replaces DigitalOcean as the deployment target. Use a **Hostinger VPS**, not shared
or managed web hosting: the application requires Docker Compose, PostgreSQL, Redis, MinIO,
ClamAV, FFmpeg workers, persistent volumes, and firewall control.

Hostinger has no Toronto VPS location. Select **New York**, the closest currently available
Hostinger VPS location to Toronto. The previous `deploy/production/digitalocean` package is
retained only as migration history and must not be used for a new deployment.

## Credential file

The repository-root `.env` is the **only owner-edited credential file**. It contains labeled
sections for application, Hostinger, release, edge, email, billing, backup, and private-Studio
inputs. Existing credentials remain in place; replace only its `DUMMY_...` values. Never send
the completed file through chat or commit it. The provider-folder `*.example.env` files remain
non-secret validation fixtures and documentation, not additional credential entry points.

Validate the dummy file without contacting Hostinger or any third party:

```bash
python3 deploy/production/hostinger/validate_config.py --mode dummy
docker compose --env-file .env \
  -f deploy/production/hostinger/compose.yml config --quiet
```

With the local staging stack running, exercise the real Hostinger Caddy image against the
staging API/web upstreams. This proves direct-origin denial, trusted public admission, private
Studio/admin denial, two-secret private admission, and `/api` path routing:

```bash
deploy/production/hostinger/verify_ingress.sh
```

Deploy mode deliberately fails until every dummy value is replaced, the Stripe key is
live, strong secrets are present, and policies are approved:

```bash
python3 deploy/production/hostinger/validate_config.py --mode deploy
```

## VPS setup

1. Create a Hostinger VPS in New York using its Ubuntu 24.04 with Docker template. The
   supplied resource profile requires at least 24 GiB RAM and 8 vCPU so persistent service
   ceilings retain 20% host headroom. Change limits only from measured load evidence.
2. Point `ORIGIN_HOSTNAME` and `STORAGE_HOSTNAME` A/AAAA records to the VPS. Route the public
   `WEB_HOSTNAME` through the geo edge. Keep the CDN and
   geo-aware Cloudflare Workers described in `../cdn` and `../geo-edge`; Hostinger is the
   origin host, while those remain security/delivery edges.
3. Enable Hostinger's managed VPS firewall with default deny. Allow TCP 22 only from the
   owner's fixed IP or Tailscale administration path, and allow TCP 80/443 plus UDP 443
   publicly. Do not expose PostgreSQL, Redis, MinIO console, or ClamAV ports.
   Caddy is the only Compose service publishing host ports. Direct web/API origin requests
   still return 404 without the separate edge credential, including requests that discover
   the VPS address. Where operationally possible, further restrict 80/443 to the edge
   provider's maintained source ranges after confirming certificate renewal behavior.
4. Install and enroll Tailscale, then deploy `../private-studio`. Its
   `PUBLIC_APP_ORIGIN` must be `https://WEB_HOSTNAME`, and its edge secret must exactly
   match `STUDIO_EDGE_SECRET` in this stack. The gateway must also supply the same
   `ORIGIN_EDGE_SECRET` used by the trusted public edge. Public `/studio` and `/api/admin`
   requests, and private requests missing either required credential, return 404.
5. Build releases on an approved builder—not on the VPS. Fill the release labels in the root
   `.env`, authenticate Docker to the selected registry outside that file, and run:

```bash
deploy/production/hostinger/build_release.sh
```

   It builds API, web, and backup images for `linux/amd64`, pushes an explicit non-`latest`
   release identifier, resolves each registry manifest digest, and atomically pins all three
   references in the mode-0600 root `.env`. Registry authentication stays outside the file.
   Review the digests, run deploy-mode validation, transfer the package and `.env` through the
   approved secret channel, then on the VPS run:

```bash
docker compose --env-file .env \
  -f deploy/production/hostinger/compose.yml pull
docker compose --env-file .env \
  -f deploy/production/hostinger/compose.yml up -d --no-build
```

6. Run the production preflight and public-edge smoke from `../README.md`, then test login,
   Studio upload, processing, playback, billing webhooks, email, CDN authorization, and
   territory enforcement before opening traffic.

## Host bootstrap and audit

Set the host-hardening labels in the root `.env`: the exact VPS hostname and a narrow IPv4
`/24` or smaller (prefer `/32`) or IPv6 `/64` or smaller SSH source.
Audit mode is read-only and emits only stable pass/fail check names:

```bash
deploy/production/hostinger/bootstrap_host.sh --mode audit
```

Run it hourly after bootstrap so Node Exporter's private textfile collector can expose the
latest pass/fail state:

```cron
7 * * * * /opt/aperture/deploy/production/hostinger/bootstrap_host.sh --mode audit >/dev/null
```

Apply mode is intentionally not automatic. It requires root, the exact confirmation phrase,
the expected current hostname, and a live SSH connection whose source belongs to the declared
allowlist. It installs/enables automatic security updates, Fail2ban and UFW; disables root,
password and keyboard-interactive SSH; retains public-key login; limits authentication; merges
Docker live-restore/no-new-privileges/log rotation; exposes only restricted SSH plus Caddy
80/443 TCP and 443 UDP; validates sshd before reload; then reruns the audit:

```bash
sudo deploy/production/hostinger/bootstrap_host.sh --mode apply
```

Keep the Hostinger web-console open and a second approved SSH session available during the
first rehearsal. Do not close the original session until a new key-authenticated connection
succeeds. Apply mode resets UFW rules, so review the script and add any separately approved
monitoring/Tailscale requirements first. It does not configure full-disk encryption: the audit
requires evidence of a `crypt` block device, and a failure remains a launch risk requiring
Hostinger/provider evidence or reprovisioning before production data exists.

Install the bounded maintenance and backup jobs in the VPS root crontab after placing this
repository at `/opt/aperture` (adjust only that explicit path if different):

```cron
*/5 * * * * flock -n /var/lock/aperture-maintenance.lock /opt/aperture/deploy/production/hostinger/operations.sh maintenance
23 * * * * flock -n /var/lock/aperture-replication.lock /opt/aperture/deploy/production/hostinger/operations.sh replicate-media
17 3 * * * flock -n /var/lock/aperture-backup.lock /opt/aperture/deploy/production/hostinger/operations.sh backup
```

Run the dependency preflight manually after migrations and before shifting traffic:

```bash
deploy/production/hostinger/operations.sh preflight
```

## Isolated restore rehearsal

Fill the restore section of the root `.env`, use a newly created empty database whose name
begins with `aperture_restore_`, and use a read-only backup identity.
The guard rejects dummy values, production-shaped database names, non-HTTPS storage, an
invalid manifest suffix, or a missing confirmation before Docker starts:

```bash
deploy/production/hostinger/operations.sh restore
```

The restore verifier binds the manifest to its dump, checks size and SHA-256 before
`pg_restore`, then verifies migration head and table count. It never creates or drops a
database.

## Immutable-image rollback

Keep at least one previously accepted API, web, and backup digest available in the registry
and pulled on the VPS. Fill the rollback section of the root `.env`, select that exact
three-digest release, and inspect it without changing traffic:

```bash
python3 deploy/production/hostinger/hostinger_rollback.py --mode inspect
```

After dual approval and migration-compatibility review, use the exact confirmation phrase
from the example and execute. The controller verifies all three images locally, atomically
changes only `API_IMAGE`, `WEB_IMAGE`, and `BACKUP_IMAGE` while preserving credential-file
mode and all other content, starts with `--no-build`, and runs the production preflight. If
startup or preflight fails, it restores the previous digest set and attempts to bring that
release back:

```bash
python3 deploy/production/hostinger/hostinger_rollback.py --mode execute
```

This does not reverse database migrations. Use only releases whose schema compatibility was
explicitly reviewed, and follow with public smoke and the bad-deployment runbook.

## Backups and recovery

Hostinger's automatic VPS backups are weekly by default and restoring one overwrites the
current server. They are not sufficient alone. The `backup` operation creates a PostgreSQL
custom dump plus checksum/migration/table-count manifest in the independent private,
versioned S3-compatible destination labeled in the root `.env`. Also configure MinIO
replication, test the existing isolated restore verifier against that destination, and record
measured RPO/RTO evidence before launch.

The replica operation copies media to a distinct HTTPS S3-compatible endpoint and bucket,
enables versioning/private access, overwrites changed objects, and deliberately never deletes
remote objects. Its validator rejects dummy, loopback/in-VPS, HTTP, and same-bucket targets.

## Container hardening and failure domains

Every service has CPU, memory, PID, and bounded JSON-log ceilings. Application and operation
containers use a read-only root filesystem, tmpfs scratch space, all Linux capabilities
dropped, and `no-new-privileges`; stateful vendor images retain only their required writable
volumes and also forbid privilege escalation. PostgreSQL, Redis, MinIO, ClamAV, API, web, and
Caddy have health checks. Only Caddy publishes host ports, mapped to unprivileged internal
ports 8080/8443.

This remains one physical VPS: application, database, queue, storage, scanner, and workers can
fail together. Resource limits reduce noisy-neighbor damage but do not provide high
availability. Weekly Hostinger snapshots, independent daily database backups, and hourly
off-site media copies reduce recovery exposure; they do not replace a tested second-node or
managed-service failover architecture if the launch SLA requires one.

## Private monitoring

Render the private Prometheus configuration after replacing credentials. The renderer writes
mode 0600 atomically and deploy mode rejects a dummy/short metrics bearer token:

```bash
python3 deploy/production/hostinger/render_monitoring.py --mode deploy
```

Prometheus, Node Exporter, and Blackbox Exporter have no published host ports. Prometheus
scrapes authenticated API metrics plus host/textfile metrics and retains at most 15 days or
10 GB. The credential-last renderer also creates a five-surface HTTPS target file covering
the public web security-header contract, API readiness response, storage readiness, CDN TLS
reachability, and the direct origin's required 404 denial. Successful maintenance,
backup, preflight, restore, and replication operations atomically publish timestamps only after
their commands return successfully. Alerts cover missing/failing host audit, root-disk pressure,
clock synchronization, and stale maintenance/backup/media replication in addition to the
existing API, database, queue, storage, playback, processing, and administrator signals.
Blackbox alerts fire on reachability/header/origin-denial failures and certificates within
14 days of expiry.

This stack evaluates rules but does not invent an alert receiver. Before launch, connect the
private Prometheus instance to an owner-approved Alertmanager/remote monitoring path through
Tailscale or another authenticated private channel, add independent probes from at least two
external regions, send synthetic alerts, and record receipt,
acknowledgement, and resolution. Never publish Prometheus, Node Exporter, or Blackbox Exporter
to the Internet.
