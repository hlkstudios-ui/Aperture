# Hostinger VPS production target

Routine application releases after the first accepted launch use the guarded GitHub-to-VPS flow
in [`docs/CONTINUOUS_DEPLOYMENT.md`](../../../docs/CONTINUOUS_DEPLOYMENT.md). This runbook remains
authoritative for the first launch, platform changes, stateful changes, and recovery.

This replaces DigitalOcean as the deployment target. Use a **Hostinger VPS**, not shared
or managed web hosting: the application requires Docker Compose, PostgreSQL, Redis, MinIO,
ClamAV, FFmpeg workers, persistent volumes, and firewall control.

The selected Hostinger US data-center option is **Boston 2** (`Boston_2`). The recommended
default is the **full** KVM 8 profile with 32 GiB RAM, 8 vCPU, and 400 GiB disk. A guarded
**compact** profile supports the owner's existing KVM 4 VPS with 16 GiB RAM, 4 vCPU, and
200 GiB disk. The previous `deploy/production/digitalocean` package is retained only as
migration history and must not be used for a new deployment.

## Release artifact boundary

The public API image is built from `apps/api/Dockerfile` and intentionally contains no FFmpeg
or FFprobe binary. The API, migration, Scene worker, maintenance, and preflight services share
that audited digest. Media processing alone uses `MEDIA_WORKER_IMAGE`, built from
`apps/api/Dockerfile.media-worker`, which installs FFmpeg and defaults to
`app.media_worker`. Both images retain the pinned Python 3.12.14/Alpine 3.24 base, upgrade
installed Alpine packages before adding runtime packages, install the same locked Python
dependencies, and run as the unprivileged `aperture` user.

The web and minimal backup runtimes have their own release digests. Caddy is built from
`caddy.Dockerfile` with Caddy 2.11.4 and patched Go dependencies, then copied into a pinned
nonroot distroless runtime. Storage is built from `storage.Dockerfile`: it compiles the exact
final MinIO Community security-release source with the reviewed dependency remediations and
uses a pinned nonroot distroless runtime. Compose never pulls a mutable upstream Caddy or MinIO
server image. `node-exporter.Dockerfile` and `blackbox-exporter.Dockerfile` likewise compile the
exact reviewed exporter releases with patched Go dependencies into pinned nonroot distroless
runtimes; Prometheus and ClamAV remain audited upstream runtime images.

An owner `.env` or previously rendered `/opt/aperture/.env` from an older release will not contain
all current image and public-address labels and therefore fails closed. Add the missing fields to
the owner file using `credentials.example.env` as the reference, run the eight-artifact build/pin
workflow, then re-render and transfer the complete mode-0600 VPS artifact. Do not patch the
sanitized VPS file in place or copy the owner credential file to the server.

## Capacity profiles

Set `HOSTINGER_VPS_PROFILE` explicitly. `full` remains the recommended production default.
`compact` is valid for a low-traffic launch, but it has less tolerance for simultaneous media
processing, malware scans, backups, and traffic spikes. It remains a single failure domain and
is not a high-availability profile.

| Profile | Hostinger plan | Provider-labeled floor | Guest-visible audit floor | Persistent-memory guard |
| --- | --- | --- | --- | --- |
| `full` | KVM 8 | 32 GiB RAM, 8 vCPU, 400 GiB disk | 31 GiB RAM, 380G root disk | At least 20% host headroom |
| `compact` | KVM 4 | 16 GiB RAM, 4 vCPU, 200 GiB disk | 15 GiB RAM, 190G root disk | At least 35% host headroom |

`HOST_MIN_MEMORY_GB` and `HOST_MIN_DISK_GB` always retain the provider-labeled plan values.
The read-only audit separately allows one GiB of guest memory reservation and up to 5% disk
provisioning/filesystem overhead. This makes the observed compact 15 GiB `/proc` memory and
193G `df` root disk valid without weakening the selected 16/200 plan contract. Readings below
15/190 for compact or 31/380 for full still fail closed.

For `compact`, set the following values together in the root `.env`. These lower labeled
service ceilings to 8.75 GiB, leaving room for Prometheus/exporters, short-lived operations,
Docker, the kernel, filesystem cache, and workload bursts:

```dotenv
HOSTINGER_VPS_PROFILE=compact
HOSTINGER_VPS_MEMORY_GB=16
HOSTINGER_VPS_VCPU=4
HOST_MIN_MEMORY_GB=16
HOST_MIN_DISK_GB=200
HOST_MIN_FREE_DISK_GB=50
POSTGRES_MEMORY_LIMIT=1280m
REDIS_MEMORY_LIMIT=256m
MINIO_MEMORY_LIMIT=1280m
CLAMAV_MEMORY_LIMIT=1280m
API_MEMORY_LIMIT=768m
MEDIA_WORKER_MEMORY_LIMIT=2g
SCENE_WORKER_MEMORY_LIMIT=1g
WEB_MEMORY_LIMIT=768m
CADDY_MEMORY_LIMIT=256m
```

Keep media-processing concurrency conservative, alert on memory pressure, and move to `full`
before sustained traffic or parallel transcodes. Do not weaken the validator or increase compact
ceilings without measured load and restore evidence.

## Public ingress address binding

Set `HOSTINGER_VPS_IP` to the provider-assigned public IPv4 address and
`HOSTINGER_VPS_IPV6` to the provider-assigned public IPv6 address. These two values are non-secret
runtime configuration: the sanitizer includes them in the exact VPS allowlist, while SSH keys,
Hostinger tokens, Tailscale credentials, and other workstation controls remain excluded.

Production Compose publishes Caddy's port 80 TCP and port 443 TCP/UDP sockets separately on both
configured public addresses. It deliberately does not publish to `0.0.0.0` or `::`. This allows
Tailscale Serve to retain its private port-443 listeners on the node's tailnet IPv4 and IPv6
addresses without colliding with public Caddy. Do not put a Tailscale address, a loopback address,
a wildcard, or a documentation address in either field. Deploy validation requires the correct IP
family and a globally routable address; rendered-topology validation requires the complete six
address/port/protocol bindings.

If Hostinger changes either public address, update the owner `.env`, re-render the mode-0600 VPS
runtime, validate it, and redeploy Compose as one reviewed operation. Never hand-edit only the
server copy.

## Credential file

The repository-root `.env` is the **only owner-edited credential file**. It contains labeled
sections for application, Hostinger, release, edge, email, billing, backup, and private-Studio
inputs. Existing credentials remain in place; replace only its `DUMMY_...` values. Never send
the completed file through chat, commit it, or transfer it to the VPS. The provider-folder
`*.example.env` files remain non-secret validation fixtures and documentation, not additional
credential entry points.

Generate only the Aperture-owned database, cache, object-store, session, edge, and monitoring
secrets locally. This command is idempotent: it fills blank/known-placeholder internal labels
and never rotates a configured value. It does not invent provider-issued credentials and does
not print generated values:

`CUSTOM_DOMAIN_EDGE_SECRET` is one of those generated internal values. The rendered VPS
environment injects it into the web and API runtimes only; store the exact same value in the
geo Worker secret manager. Do not add it to Caddy, a browser bundle, or customer DNS records.

```bash
python3 deploy/production/hostinger/prepare_vps_env.py generate --input .env
```

The VPS receives a separate machine-rendered `/opt/aperture/.env` containing only the exact
Compose runtime and host-audit allowlists. The two non-secret public bind addresses are included
because Compose consumes them. The artifact contains no Hostinger API token, local SSH user/key
configuration, build inputs, one-shot Cloudflare DNS/preflight credentials, Tailscale control
credentials, or one-shot restore/rollback inputs. A dedicated Cloudflare Custom Hostnames/KV
runtime token is rendered only when custom domains are enabled. Treat both files as secrets, but
do not confuse the sanitized runtime artifact with the owner source file.

`HOSTINGER_API_TOKEN` is intentionally optional after provisioning. Keep it empty or revoked for
release builds, source validation, runtime rendering, deployment, and steady-state operations.
If a local tool is going to call the Hostinger control plane, create a narrowly scoped short-lived
token and make that tool request the explicit credential gate before its first request:

```bash
python3 deploy/production/hostinger/validate_config.py --input .env --mode deploy \
  --require-hostinger-api-token
```

The gate rejects an empty or placeholder token without printing it. It cannot prove offline that
a non-empty token is still active, so the API caller must also fail on Hostinger authentication or
authorization errors. Revoke the token after the operation and atomically clear its local value:

```bash
python3 deploy/production/hostinger/prepare_vps_env.py clear-hostinger-token --input .env
```

Treat Tailscale enrollment and control-plane credentials the same way. After the one-time node
enrollment has succeeded, revoke the auth key and clear its local label. After any Tailscale API
operation, revoke the API key and clear that label too. Neither credential belongs in a rendered
VPS or private-gateway artifact:

```bash
python3 deploy/production/hostinger/prepare_vps_env.py clear-tailscale-auth-key --input .env
python3 deploy/production/hostinger/prepare_vps_env.py clear-tailscale-api-key --input .env
```

### Cloudflare for SaaS readiness

Custom domains are optional. Keep both `CUSTOM_DOMAINS_ENABLED=false` and
`CUSTOM_DOMAIN_INFRASTRUCTURE_READY=false` while building the Cloudflare topology; the canonical
`WEB_HOSTNAME` remains available in that state. Use four different credentials:

- `CLOUDFLARE_API_TOKEN` is the short-lived DNS-cutover token described in the root example.
- `CLOUDFLARE_CUSTOM_DOMAIN_PREFLIGHT_API_TOKEN` is a short-lived, read-only owner token with
  access to fallback-origin state, zone DNS records, Worker routes, Worker script settings, and
  Worker custom-domain mappings.
- `CLOUDFLARE_CUSTOM_HOSTNAMES_API_TOKEN` is the least-privilege long-lived API token for Custom
  Hostnames and the one `SITE_DOMAINS` KV namespace. The preflight performs one safe Custom
  Hostnames list and one KV key-list request with it, proving read access before it reaches the VPS.
- `CLOUDFLARE_TURNSTILE_API_TOKEN` is the separate long-lived token limited to Turnstile Sites
  Write for the login widget. It is required only when CAPTCHA and custom domains are both enabled;
  the preflight uses its read access to inspect that widget without changing it.

Configure the active SaaS fallback as `CUSTOM_DOMAIN_FALLBACK_ORIGIN` (which must exactly equal
`ORIGIN_HOSTNAME`), and point the proxied Aperture-owned `CUSTOM_DOMAIN_CNAME_TARGET` CNAME to that
fallback. Deploy the geo and CDN Workers under the configured script names. Both must bind the
exact same `SITE_DOMAINS` namespace and have `CUSTOM_DOMAINS_ENABLED=true`; the geo Worker must also
have `GEO_ASSERTION_SECRET`, `ORIGIN_EDGE_SECRET`, and `CUSTOM_DOMAIN_EDGE_SECRET` secret bindings.
Create exactly one `*/*` zone route targeting the geo Worker. Before that wildcard, create exactly
one more-specific no-Worker route for each of `ORIGIN_HOSTNAME/*`, `STORAGE_HOSTNAME/*`, and
`CDN_HOSTNAME/*`. A no-Worker route is a Cloudflare route with no script association; do not put it
in the geo Worker's Wrangler route list, which would associate it with that Worker. Finally, map
`CDN_HOSTNAME` to the CDN Worker as a Worker Custom Domain. These exclusions prevent the wildcard
from intercepting origin calls or winning ahead of the CDN Custom Domain. When CAPTCHA is enabled,
the configured Turnstile widget must contain the exact canonical `WEB_HOSTNAME`. This non-Enterprise
launch caps that widget at ten hostnames, so `CUSTOM_DOMAIN_MAX_PER_SITE=9` reserves its first slot
for the canonical host.

Run the GET-only verifier from the owner workstation. It emits one stable, secret-free JSON record
and exits nonzero unless every boundary above, both custom-domain runtime-token reads, and the
Turnstile widget/capacity checks pass:

```bash
python3 deploy/production/hostinger/cloudflare_saas_preflight.py --input .env
```

Only after it returns `"ready":true` may the owner set
`CUSTOM_DOMAIN_INFRASTRUCTURE_READY=true`. Set `CUSTOM_DOMAINS_ENABLED=true` only when the optional
feature should be exposed; validation rejects that flag without the readiness attestation. Set the
readiness label back to false before changing the fallback, routes, script names, custom domain,
namespace, bindings, or credentials, then rerun the preflight. Revoke and clear each one-shot token
after its job; never clear the runtime token while the provider is enabled:

```bash
python3 deploy/production/hostinger/prepare_vps_env.py clear-cloudflare-dns-token --input .env
python3 deploy/production/hostinger/prepare_vps_env.py clear-cloudflare-preflight-token --input .env
```

Customer authentication stays on the storefront origin. Configure both values for each
OAuth provider you enable and register its `/api/gateway/auth/oauth/{provider}/callback`
URL. When `CAPTCHA_REQUIRED=true`, both Turnstile keys are mandatory: the build embeds only
`NEXT_PUBLIC_TURNSTILE_SITE_KEY` in the web image, while `TURNSTILE_SECRET_KEY` and all OAuth
credentials are injected only into API containers. Enabling custom domains with CAPTCHA also
requires the API-only `CLOUDFLARE_TURNSTILE_API_TOKEN` and the standard-widget hostname limit.
Customer and remembered-account cookies remain host-only; do not add `SESSION_COOKIE_DOMAIN` to
this production stack.

The optional launch writing assistant is off by default. Enable it only after assigning a
dedicated OpenAI project/service key, approving the account's data-retention settings, setting
spend limits and alerts, and recording key rotation and emergency revocation ownership. Keep
`OPENAI_API_KEY` in the API container only, set `BRAND_AI_PROVIDER=openai`, use the tested
`gpt-5-mini` model, restart the API, and make one non-sensitive request from the private owner
Studio. To disable it, set the provider back to `disabled` and restart; revoke the key if exposure
is suspected.

Validate the dummy file without contacting Hostinger or any third party:

```bash
python3 deploy/production/hostinger/validate_config.py --mode dummy
docker compose --env-file .env \
  -f deploy/production/hostinger/compose.yml config --quiet
```

With the local staging stack running, exercise the real Hostinger Caddy image against the
staging API/web upstreams. This proves direct-origin denial, trusted public admission, private
Studio/admin denial, two-secret private admission, same-origin gateway routing, and the
direct API allowlist:

```bash
deploy/production/hostinger/verify_ingress.sh
```

Deploy mode deliberately fails until every active deployment dummy value is replaced, strong
secrets are present, and policies are approved. This release pins `BILLING_PROVIDER=disabled` in
Compose, so both Stripe values stay empty and Stripe is never contacted. Enabling payments requires
a separate reviewed release, live credentials, and billing acceptance. Run validation only on the
approved local builder. Source-only labels remain local, but a cleared Hostinger token does not
block this post-provisioning validation:

```bash
python3 deploy/production/hostinger/validate_config.py --mode deploy
```

## VPS setup

1. Reinstall the selected Boston 2 VPS with Hostinger's Ubuntu 24.04 Docker template. Use the
   recommended `full` KVM 8 profile for new capacity, or the documented `compact` KVM 4
   profile for the approved existing-host reuse. The validator enforces each profile's capacity
   floor and memory reserve. Change limits only from measured load evidence.
2. Point `ORIGIN_HOSTNAME` and `STORAGE_HOSTNAME` A/AAAA records to the VPS. Route the public
   `WEB_HOSTNAME` through the geo edge. Keep the CDN and
   geo-aware Cloudflare Workers described in `../cdn` and `../geo-edge`; Hostinger is the
   origin host, while those remain security/delivery edges. Set the CDN Worker's
   `ORIGIN_API` to `https://ORIGIN_HOSTNAME/api`, not the geo-routed public hostname, so its
   dedicated `CDN_ORIGIN_SECRET` reaches the protected media allowlist unchanged.
   Optional customer domains terminate TLS at Cloudflare for SaaS and route through the geo
   Worker. Do not add customer hostnames to this Caddyfile or point them directly at the VPS.
   Caddy continues to obtain certificates only for the Aperture-owned web, origin, and storage
   hostnames, while the Worker-provided trusted public hostname is forwarded to the web runtime.
3. Enable Hostinger's managed VPS firewall with default deny. Allow TCP 22 only from the
   owner's fixed IP or Tailscale administration path, and allow TCP 80/443 plus UDP 443
   publicly. Do not expose PostgreSQL, Redis, MinIO console, or ClamAV ports.
   Caddy is the only Compose service publishing host ports. Direct web/API origin requests
   still return 404 without the separate edge credential, including requests that discover
   the VPS address. Where operationally possible, further restrict 80/443 to the edge
   provider's maintained source ranges after confirming certificate renewal behavior.
4. Build releases on an approved builder before rendering or deploying either runtime. Never
   build on the VPS. Review and commit the exact source first: the publisher rejects tracked,
   staged, or non-ignored untracked changes before Docker or the registry is contacted. Ignored
   runtime files such as `.env` remain allowed. Fill the release labels in the root `.env`,
   authenticate Docker to the selected registry outside that file, and run:

```bash
deploy/production/hostinger/build_release.sh
```

   It reserves a one-use release identifier, proves all eight exact registry tags are absent,
   builds API, media-worker, web, backup, Caddy, storage, node-exporter, and Blackbox images for
   `linux/amd64` with provenance and SBOM attestations, and resolves each digest once. After all
   eight distinct references validate, it writes a secret-free manifest/checksum commit marker
   and only then atomically pins them in the mode-0600 root `.env`. Registry authentication stays
   outside the file. A failed or interrupted attempt burns the reserved release identifier so it
   cannot be reused ambiguously.

   Pull and rescan all eight images after pinning. Retain the reports with the release evidence,
   review every unfixed finding, and do not infer that the worker's FFmpeg findings affect the
   FFmpeg-free API image. Also retain the Caddy version and MinIO release identity from the
   first-party edge/storage artifacts. Use the literal dotenv reader rather than sourcing the
   credential file:

```bash
for image_label in \
  API_IMAGE MEDIA_WORKER_IMAGE WEB_IMAGE BACKUP_IMAGE \
  CADDY_IMAGE STORAGE_IMAGE NODE_EXPORTER_IMAGE BLACKBOX_IMAGE
do
  image=$(python3 deploy/production/hostinger/read_env.py \
    --input .env --label "$image_label")
  docker pull "$image"
  docker scout cves "$image"
done

api_image=$(python3 deploy/production/hostinger/read_env.py --input .env --label API_IMAGE)
media_worker_image=$(python3 deploy/production/hostinger/read_env.py --input .env --label MEDIA_WORKER_IMAGE)
caddy_image=$(python3 deploy/production/hostinger/read_env.py --input .env --label CADDY_IMAGE)
storage_image=$(python3 deploy/production/hostinger/read_env.py --input .env --label STORAGE_IMAGE)
node_exporter_image=$(python3 deploy/production/hostinger/read_env.py --input .env --label NODE_EXPORTER_IMAGE)
blackbox_image=$(python3 deploy/production/hostinger/read_env.py --input .env --label BLACKBOX_IMAGE)
docker run --rm --entrypoint sh "$api_image" -ec '! command -v ffmpeg && ! command -v ffprobe'
docker run --rm --entrypoint sh "$media_worker_image" -ec 'command -v ffmpeg && command -v ffprobe'
docker run --rm "$caddy_image" version
docker run --rm "$storage_image" --version
docker run --rm "$node_exporter_image" --version
docker run --rm "$blackbox_image" --version
```

   Review the digests and run the source and host-input validation locally:

```bash
python3 deploy/production/hostinger/validate_config.py --input .env --mode deploy
python3 deploy/production/hostinger/validate_host_hardening.py --input .env --mode apply
```

   Render both least-privilege runtime artifacts only after the eight digests have been pinned.
   The public and private artifacts must come from that same owner `.env`; compare their literal
   `CADDY_IMAGE` values before transfer. Keep both mode-0600 files outside synced folders and
   arrange deletion even if transfer fails:

```bash
APERTURE_VPS_ENV=$(mktemp "${TMPDIR:-/tmp}/aperture-vps.XXXXXX")
APERTURE_STUDIO_ENV=$(mktemp "${TMPDIR:-/tmp}/aperture-studio.XXXXXX")
trap 'rm -f -- "$APERTURE_VPS_ENV" "$APERTURE_STUDIO_ENV"' EXIT
python3 deploy/production/hostinger/prepare_vps_env.py render \
  --input .env --output "$APERTURE_VPS_ENV"
python3 deploy/production/private-studio/render_runtime.py \
  --input .env --output "$APERTURE_STUDIO_ENV"
python3 deploy/production/hostinger/validate_caddy_coupling.py \
  --public-env "$APERTURE_VPS_ENV" --private-env "$APERTURE_STUDIO_ENV"
```

   Transfer the repository/package separately to `/opt/aperture`. Copy only the two rendered
   artifacts through the encrypted SSH channel, install them under root ownership, and remove the
   incoming and local temporary copies. Replace the example SSH target with the approved VPS
   identity:

```bash
scp -p "$APERTURE_VPS_ENV" root@origin.example.com:/root/aperture-vps.env.incoming
scp -p "$APERTURE_STUDIO_ENV" root@origin.example.com:/root/aperture-studio.env.incoming
ssh root@origin.example.com \
  'set -eu; trap "rm -f /root/aperture-vps.env.incoming /root/aperture-studio.env.incoming" EXIT; install -o root -g root -m 0600 /root/aperture-vps.env.incoming /opt/aperture/.env; install -o root -g root -m 0600 /root/aperture-studio.env.incoming /opt/aperture/deploy/production/private-studio/runtime.local.env'
rm -f -- "$APERTURE_VPS_ENV" "$APERTURE_STUDIO_ENV"
trap - EXIT
```

   On the VPS, validate the sanitized file, prove Compose can interpolate it, and pull the
   immutable release. On a reused host, complete the
   [legacy volume ownership procedure](#legacy-caddyminio-volume-ownership) before `up`; the
   audit is a no-op when the exact managed volume set is absent on a freshly wiped host.
   The legacy procedure includes the restarted-stack checks. On a fresh host, continue with the
   `up` command below after `pull`.

```bash
cd /opt/aperture
python3 deploy/production/hostinger/prepare_vps_env.py validate-runtime --input .env
deploy/production/hostinger/bootstrap_host.sh --mode audit
docker compose --env-file .env \
  -f deploy/production/hostinger/compose.yml config --quiet
docker compose --env-file .env \
  -f deploy/production/hostinger/compose.yml pull
docker compose --env-file .env \
  -f deploy/production/hostinger/compose.yml up -d --no-build --wait --wait-timeout 600
docker compose --env-file deploy/production/private-studio/runtime.local.env \
  -f deploy/production/private-studio/compose.yml pull
docker compose --env-file deploy/production/private-studio/runtime.local.env \
  -f deploy/production/private-studio/compose.yml up -d --no-build --wait --wait-timeout 120
python3 deploy/production/hostinger/validate_caddy_coupling.py \
  --public-env .env \
  --private-env deploy/production/private-studio/runtime.local.env \
  --check-running
```

   Install and enroll Tailscale before the final two private-gateway commands, then revoke and
   clear the enrollment credential as documented above. `PUBLIC_APP_ORIGIN` must be
   `https://WEB_HOSTNAME`; `STUDIO_EDGE_SECRET` and `ORIGIN_EDGE_SECRET` must match the public
   stack while remaining independent of each other. Confirm the gateway binds only
   `127.0.0.1:8080` before enabling Tailscale Serve.

   `CADDY_IMAGE` is a coupled public/private release input. For a normal release, re-render both
   artifacts from the resulting owner release set, transfer them together, and redeploy both
   Compose projects. The rollback controller performs the equivalent private update and running
   coupling check automatically for a Caddy rollback or compensation. No workflow is complete
   while the private Studio gateway runs a different Caddy digest.

   Do **not** rerun `validate_config.py` against `/opt/aperture/.env`: that validator is for the
   owner source and correctly requires its source-only Hostinger/control-plane label set (the
   Hostinger token label may be empty after provisioning). The
   `validate-runtime` command enforces the runtime file's exact label set and the same applicable
   production and host-hardening checks without requiring or reconstructing a real Hostinger API
   token. `bootstrap_host.sh` and the steady-state maintenance, backup, replication, and preflight
   operations continue to read this sanitized `/opt/aperture/.env`.

5. Run the production preflight and public-edge smoke from `../README.md`, then test login,
   Studio upload, processing, playback, email, CDN authorization, territory enforcement, and
   the fail-closed checkout, billing-portal, payout, and Stripe-webhook responses before opening
   traffic. The preflight must report `payments_intentionally_disabled` without contacting Stripe.

## Legacy Caddy/MinIO volume ownership

The first-party Caddy and MinIO images run as UID/GID 65532. A named volume created by an older
upstream image can retain a different owner and make the hardened container fail at startup. Do
not run a broad host-path `chown`, guess a Compose project prefix, or use `docker volume ls` output
as a mutation target. `migrate_volume_ownership.py` accepts only the three exact volumes resolved
by the `aperture-production` Compose model, verifies both Compose labels on every volume, and uses
only a digest-pinned BusyBox helper with no network. If all three volumes are absent, both audit and
migrate return the explicit `no_op_fresh_volume_set_absent` result without pulling a helper,
requiring snapshot evidence, or creating a volume. A partial set fails closed.

Before the maintenance window, prove the independent database/object backups are current and
pull the exact helper while the application is still running:

```bash
cd /opt/aperture
helper_image=$(python3 deploy/production/hostinger/migrate_volume_ownership.py helper-image)
docker pull "$helper_image"
docker image inspect "$helper_image" >/dev/null
```

Freeze uploads, processing, publishing, migrations, and maintenance jobs. Stop this Compose
project without `--volumes`; the private Studio project can remain online but will receive 404s
until the public stack returns. Then create a Hostinger VPS snapshot, wait for the provider to
report it as fully `ready`, and record that completed check in a root-owned mode-0600 JSON file.
The evidence record binds the exact stopped-host volume set but cannot independently prove a
provider claim, so retain the Hostinger snapshot-status capture with the change record:

```bash
docker compose --env-file .env \
  -f deploy/production/hostinger/compose.yml down --remove-orphans
sudo install -o root -g root -m 0600 /dev/null /root/aperture-volume-snapshot.json
sudoedit /root/aperture-volume-snapshot.json
```

```json
{
  "schema_version": 1,
  "provider": "hostinger",
  "snapshot_id": "replace-with-completed-snapshot-id",
  "status": "ready",
  "verified_at": "2026-08-30T12:00:00Z",
  "verified_by": "release-operator",
  "hostname": "aperture-origin",
  "compose_project": "aperture-production",
  "volumes": [
    "aperture-production_caddy-config",
    "aperture-production_caddy-data",
    "aperture-production_minio-data"
  ]
}
```

Use the real `EXPECTED_HOSTNAME`, verifier identity, snapshot ID, and current UTC time. Evidence
older than 24 hours, future-dated evidence, a non-ready snapshot, insecure/symlink evidence, a
running public project, a target volume mounted by any other running container, any label/name
mismatch, a partial volume set, or an unpinned/missing helper all stop the operation. Audit first.
If it reports an ownership mismatch, run the single
authorized mutation; it recursively changes only those three labeled volumes and then performs
read-only recursive ownership checks plus a create/stat/remove probe as UID/GID 65532:

```bash
sudo python3 deploy/production/hostinger/migrate_volume_ownership.py audit --input .env
sudo python3 deploy/production/hostinger/migrate_volume_ownership.py migrate \
  --input .env \
  --snapshot-evidence /root/aperture-volume-snapshot.json \
  --confirm MIGRATE_APERTURE_CADDY_MINIO_VOLUMES_TO_UID_65532
```

Start only the already pinned release, wait for health, verify the actual Caddy and MinIO
containers use the rendered images as nonroot and mount only the exact read-write volumes, then
run the application preflight. If the start verification fails, stop the public project again and
recover from the verified snapshot or an approved clone rehearsal; do not improvise a second
filesystem mutation:

```bash
docker compose --env-file .env \
  -f deploy/production/hostinger/compose.yml up -d --no-build --wait --wait-timeout 600
python3 deploy/production/hostinger/migrate_volume_ownership.py verify-start --input .env
deploy/production/hostinger/operations.sh preflight
```

## Host bootstrap and audit

Set the host-hardening labels in the root `.env`: the exact VPS hostname and a narrow IPv4
`/24` or smaller (prefer `/32`) or IPv6 `/64` or smaller SSH source.
Keep capacity labels at the advertised plan values; do not copy rounded guest-visible values
from `/proc` or `df` into the configuration.
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
allowlist. Before Fail2ban can start, it installs a late-sorting managed sshd jail override at
`/etc/fail2ban/jail.d/zz-aperture-sshd.local`. That jail preserves loopback and adds exactly
`SSH_ALLOWED_CIDR` to sshd `ignoreip`; it does not exempt any other source or change other
jails. The script validates the merged Fail2ban configuration, finishes UFW, restarts Fail2ban,
and clears any pre-existing sshd ban for the already CIDR-validated live operator IP. It also
installs/enables automatic security updates and UFW; installs the managed SSH policy as
`00-aperture-hardening.conf` so it precedes cloud-init/vendor drop-ins,
removes only Aperture's obsolete `60-aperture-hardening.conf`, verifies effective `sshd -T`
values, and disables root,
password and keyboard-interactive SSH; retains public-key login; limits authentication; merges
Docker live-restore/no-new-privileges/log rotation; exposes only restricted SSH plus Caddy
80/443 TCP and 443 UDP; validates sshd before reload; then reruns the audit. The UFW audit
normalizes column spacing but still requires an exact network match for `SSH_ALLOWED_CIDR` and
fails if any SSH rule admits `Anywhere`, `0.0.0.0/0`, or `::/0`:

```bash
sudo deploy/production/hostinger/bootstrap_host.sh --mode apply
```

Keep the Hostinger web-console open and a second approved SSH session available during the
first rehearsal. Do not close the original session until a new key-authenticated connection
succeeds. Apply mode resets UFW rules, so review the script and add any separately approved
monitoring/Tailscale requirements first. It does not configure full-disk encryption: the audit
requires evidence of a `crypt` block device, and a failure remains a launch risk requiring
Hostinger/provider evidence or reprovisioning before production data exists.

If SSH is already blocked by an earlier Fail2ban policy, widening the Hostinger firewall or UFW
does not remove the Fail2ban ban. Recover through the Hostinger console, install/rerun this
updated managed policy, and verify `fail2ban-client get sshd ignoreip` contains the approved
source before testing a second SSH session. Do not leave port 22 open to the world as a bypass.

Install the bounded maintenance and backup jobs in the VPS root crontab only after the
versioned release layout and `/opt/aperture/current` symlink exist. Every external stateful
operation uses the controller's one shared lock, so it skips instead of racing a deployment,
migration, backup, or symlink switch. The controller's own predeployment backup calls the
operation directly while already holding this lock and must not reacquire it:

```cron
*/5 * * * * flock -n /opt/aperture/shared/production-deploy.lock /opt/aperture/current/deploy/production/hostinger/operations.sh maintenance
23 * * * * flock -n /opt/aperture/shared/production-deploy.lock /opt/aperture/current/deploy/production/hostinger/operations.sh replicate-media
17 3 * * * flock -n /opt/aperture/shared/production-deploy.lock /opt/aperture/current/deploy/production/hostinger/operations.sh backup
```

Run the dependency preflight manually after migrations and before shifting traffic:

```bash
deploy/production/hostinger/operations.sh preflight
```

## Isolated restore rehearsal

Do not add restore authorization or the read-only restore identity to the owner `.env`, the
sanitized `production.env`, or a versioned release. Copy `restore.example.env` to a temporary
file on the owner workstation and fill its exact eight-label allowlist. Use a newly created
empty database whose name begins with `aperture_restore_` and a backup-store identity that can
read objects but cannot write or delete them.

Transfer that file through the encrypted administration channel, then install it into the
controller-owned shared boundary. The fixed path prevents a release from retaining the
one-shot authorization:

```bash
sudo install -o root -g root -m 0600 /root/aperture-restore.env.incoming \
  /opt/aperture/shared/restore.env
```

Run the rehearsal under the same lock used by deployments and other stateful operations:

```bash
sudo flock -n /opt/aperture/shared/production-deploy.lock \
  /opt/aperture/current/deploy/production/hostinger/operations.sh restore
```

Before Docker starts, the launcher requires a root-owned, non-symlink mode-0600 input in an
owner-protected directory and rejects missing, duplicate, extra, or dummy labels,
production-shaped database names, non-HTTPS storage, an invalid manifest suffix, or a missing
confirmation. Only the eight allowlisted values enter the restore container; the second
Compose input exists for this command only and does not modify the live production runtime.

The restore verifier binds the manifest to its dump, checks size and SHA-256 before
`pg_restore`, then verifies migration head and table count. It never creates or drops a
database. Remove `/opt/aperture/shared/restore.env` after recording the rehearsal evidence.

## Immutable-image rollback

This section applies only to a manually managed host that has not been initialized with the
CI release-controller layout. Once `/opt/aperture/current`, the shared production runtime, or
the production launch marker exists, `hostinger_rollback.py` refuses both `inspect` and
`execute` before reading release input, inspecting images, editing files, or invoking Docker.
It is not compatible with the controller's versioned release directories and shared runtime
files.

For CI-managed production, a failed rollout is automatically compensated by
`deploy_release.py`. To replace an already active bad application release, create a reviewed
Git revert commit, push or merge it to `main`, and approve the resulting protected production
deployment. That builds a new immutable candidate and moves forward through the same backup,
runtime update, health, coupling, smoke, history, and compensation controls. Never force-push
`main`, manually repoint `/opt/aperture/current`, edit `/opt/aperture/shared/*.env`, or use the
legacy command below as a shortcut. See
[`docs/CONTINUOUS_DEPLOYMENT.md`](../../../docs/CONTINUOUS_DEPLOYMENT.md#recover-an-active-bad-release)
for the exact forward-revert workflow and migration warning.

On a pre-controller manually managed host only, keep at least one previously accepted API,
media-worker, web, backup, Caddy, storage, node-exporter, and Blackbox digest available in the
registry and pulled on the VPS. Fill the rollback section of the root `.env`, select that exact
eight-artifact release, and inspect it without changing traffic:

```bash
python3 deploy/production/hostinger/hostinger_rollback.py --mode inspect
```

After dual approval and migration-compatibility review, use the exact confirmation phrase
from the example and execute. The controller verifies all eight images locally, atomically changes
`API_IMAGE`, `MEDIA_WORKER_IMAGE`, `WEB_IMAGE`, `BACKUP_IMAGE`, `CADDY_IMAGE`,
`STORAGE_IMAGE`, `NODE_EXPORTER_IMAGE`, and `BLACKBOX_IMAGE` while preserving credential-file mode
and all other content, starts with `--no-build`, and runs the production preflight. A changed
`STORAGE_IMAGE` additionally requires all three exact compatibility, recoverable-snapshot, and
clone-rehearsal confirmations from `rollback.example.env`; enter them only after recording that
evidence against the exact target digest. The controller does not create or validate those
external state-safety artifacts itself.

If `CADDY_IMAGE` changes, the controller first proves that the public and private artifacts and
running gateways share the current digest. It then updates both runtime files, redeploys the public
and private Compose projects, waits for the private gateway, runs preflight, and verifies the
running Caddy coupling. If any target step fails, it restores both runtime files, independently
redeploys both projects, reruns preflight, and rechecks coupling. Its secret-free failure event
distinguishes the exact target or compensation stage:

```bash
python3 deploy/production/hostinger/hostinger_rollback.py --mode execute
```

The controller leaves the private project untouched when `CADDY_IMAGE` is unchanged. For every
Caddy change or automatic recovery, rollback is complete only after its built-in running-coupling
check passes. Retain an independent passing result with the final release or rollback evidence:

```bash
python3 deploy/production/hostinger/validate_caddy_coupling.py \
  --public-env .env \
  --private-env deploy/production/private-studio/runtime.local.env \
  --check-running
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
