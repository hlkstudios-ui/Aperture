# Continuous deployment

After the one-time production setup is accepted, Aperture uses one release path:

1. Commit an improvement and push it to GitHub.
2. The `Quality and security` workflow tests the exact pushed commit.
3. A passing `main` commit publishes four new application images by immutable digest. The
   accepted Caddy, storage, and monitoring images are copied without rebuilding them.
4. The protected `production` environment asks the release owner for approval.
5. An ephemeral, repository-bound Tailscale identity reaches the dedicated VPS deploy account.
6. SSH copies the payload once into a root-owned job and starts a transient systemd service. GitHub
   polls a root-owned status record; closing SSH, losing the tailnet path, or cancelling the runner
   does not terminate the deploy or its recovery. If the VPS reboots mid-transaction, the enabled
   boot-recovery service resumes compensation from the same journal after Docker and the network
   return.
7. The VPS takes an off-site backup, deploys the exact checksum-bound release, waits for both
   Compose projects, runs the production preflight and public HTTPS smoke test, and writes the
   root-owned acceptance record. A failed application rollout restores the previous application
   references and reruns the same checks.
8. A root-owned daily systemd timer performs bounded release cleanup without widening the deploy
   account's authority or using Docker prune.

There is no recurring ZIP upload, FTP copy, manual Docker build, or VPS restart. Saving a local
file alone does not publish it: the change must still be committed and pushed (normally through a
pull request into `main`).

## Fail-closed boundaries

- `PRODUCTION_DEPLOY_ENABLED` defaults to `false`. Quality checks still run while publishing and
  deployment remain disabled.
- GitHub receives no production dotenv, Hostinger token, Cloudflare token, database password,
  Stripe key, owner Tailscale key, or registry pull credential. The publish job uses its scoped
  `GITHUB_TOKEN`; the deploy job has one dedicated SSH private key.
- The source payload contains only the controller's explicit deployment-file allowlist. It cannot
  include `.env`, Redis dumps, caches, arbitrary repository files, symlinks, or traversal paths.
- The manifest and source archive have separate SHA-256 records. The manifest binds the full
  source commit and all eight registry digests.
- Routine releases may advance only API, media worker, web, and backup images. Any changed Caddy,
  storage, exporter, Compose, alert, or privileged validation file is refused by the VPS.
- A commit that changes `apps/api/migrations/` is refused unless the protected environment variable
  `APERTURE_APPROVED_MIGRATION_SHA` equals that one exact commit after compatibility review.
- Payments remain disabled by the production Compose contract. This workflow cannot enable them.
- Production jobs are serialized and are never cancelled by a newer push. The VPS also holds a
  deployment lock for the complete transaction. A systemd deploy or recovery waits up to 30
  minutes for a shared backup/maintenance lock instead of treating ordinary cron overlap as an
  immediate release failure; it still fails closed after that bound.
- `/opt/aperture/current` is valid only when its source marker, runtime snapshot, live public and
  private runtimes, and mode-0600 record in `/opt/aperture/release-history/<release-id>.json` all
  agree. This includes the manually launched baseline.
- Before the first live file change, the controller durably records the accepted predecessor and
  root-only copies of both runtime files in `/opt/aperture/deploy-transaction`. An interrupted
  systemd worker restarts, compensates from that journal, and reports failure. If the journal is
  malformed or compensation cannot complete, source reporting and every later deployment refuse
  to proceed until an owner resolves it. Completed journal removal first renames the canonical
  directory to `/opt/aperture/deploy-transaction.completed` and fsyncs its parent. A crash during
  later tombstone deletion cannot replay compensation: boot recovery or the next start validates
  and finishes that deletion, while an unexpected tombstone entry still fails closed.
- Journal metadata is staged as one root-owned mode-0600 inode beside (not inside) the exact
  three-file journal, fsynced, and atomically replaced. Recognized crash debris is removed only
  while holding the shared production lock. Acceptance and failed-attempt records use flushed
  pending inodes plus no-replace hard-link publication and parent-directory fsync; malformed,
  multiply linked, wrongly owned, permissive, symlinked, or unexpected state is never repaired by
  guesswork. A compensated release has its candidate acceptance removed even if failure occurs
  after publication during journal cleanup.

## Recover an active bad release

If a rollout fails its checks or its worker is interrupted, the VPS controller automatically restores the previous shared
runtimes and `/opt/aperture/current` target, redeploys that release, and repeats preflight,
Caddy-coupling, and public HTTPS smoke checks. The transient systemd unit is
`aperture-production-deploy.service`; GitHub reads the result through the controller's restricted
`--status` mode rather than trusting `systemctl` or service logs. During reboot, GitHub tolerates
temporary SSH failures, reissues the idempotent `--start` reconciliation before each status read,
and continues polling. The active-source query also uses bounded backoff for a short shared-lock
overlap. The persistent
`aperture-deploy-recovery.service` runs only when
the canonical journal or its committed `.completed` tombstone is a directory. It derives an
interrupted release identity only from the validated canonical root-owned journal, restores the
accepted predecessor, and publishes a terminal failed status with completed recovery. A committed
tombstone is cleanup state and never triggers compensation. Do not remove
`/opt/aperture/deploy-transaction`, repoint `current`, or start a second deployment while
compensation is running.

Public submissions are serialized by a short root-owned start lock, and all status publication,
crash-temp cleanup, and GC status reconciliation share a separate short root-owned status lock.
The persistent recovery path acquires the production lock before it inspects, cleans, or reports
any journal state. A surviving canonical journal always outranks a terminal-looking status: the
worker leaves recovery nonterminal and exits nonzero, systemd retries without requiring a reboot,
and `--start` triggers persistent recovery instead of returning the stale terminal result. If the
accepted release is already live but only the final `pass` status write failed, the worker also
exits nonzero and its idempotent restart validates current plus the acceptance record before
retrying `pass`; it never rewrites that condition as a deployment failure.

Database migrations are forward-only. If a later rollout check fails after the candidate's
migration completed, compensation restores the accepted predecessor runtime and `current` link
but never starts that predecessor's `migrate` service. Before any predecessor application starts,
the controller validates the exact rendered 19-service Compose graph (including the `operations`
profile), then uses exact `docker compose rm --stop --force migrate` semantics to stop and remove
any target migration container without executing it. This also releases the failed API image once
the predecessor application containers replace the candidate containers. Recovery then uses
explicit `--no-deps` service allowlists in stateful, idempotent `minio-init`, application, and
edge/monitoring phases. The initializer runs attached with `--exit-code-from minio-init`; the
long-running phases use bounded health waits. The five operations-profile services and `migrate`
are absent from every recovery `up` allowlist. A missing, added, reprofiled, rewired, or
runtime-image-mismatched service makes compensation fail closed with the transaction journal
intact for systemd recovery.

If a release passed deployment but an application regression is found later, roll it forward
through the same audited path. Create a normal revert commit for the bad application change,
push or merge that commit to `main`, let all checks build a new immutable candidate, and approve
the protected `production` deployment. For a single bad commit, the local Git steps are:

```sh
git switch main
git pull --ff-only origin main
git revert <bad-commit-sha>
git push origin main
```

Review database compatibility before reverting code that accompanied a migration. The workflow
requires the exact new commit in `APERTURE_APPROVED_MIGRATION_SHA` whenever the migration tree
differs from the active production commit, and neither Git revert nor the deployment controller
reverses database schema or data. Do not force-push `main`, manually repoint
`/opt/aperture/current`, edit either shared runtime, or run `hostinger_rollback.py` on a
CI-managed host. The legacy rollback program detects the controller layout and refuses both
inspection and execution before reading runtime state or invoking Docker.

## Bounded host garbage collection

The installer enables `aperture-deploy-gc.timer`. It runs daily with a randomized delay and is
persistent across downtime, but its service is condition-gated on both the production launch
marker and `/opt/aperture/current`; an unlaunched host therefore does not enter a restart loop.
`aperture-deploy-gc.service` executes the hidden `--gc` controller mode as host root. That mode
rejects sudo provenance, takes the same production lock with the same 30-minute bound, validates
the current release, live runtimes, acceptance chain, and root-owned paths, and refuses to run
while a canonical deployment transaction exists.

Each pass preserves the current accepted release and up to two accepted predecessors, including
their complete release directories and all four application image references. It retains the 50
newest accepted records as an audit window. It retains a queued or running status while the fixed
transient unit owns that exact release. After 48 hours, an active-looking status with no unit and
no journal owner is reconciled to `fail/abandoned`; the already accepted current release is instead
reconciled to `pass`. It also retains the 50 newest terminal statuses, protected-release statuses,
and terminal statuses younger than seven days.
Older accepted release snapshots and records outside those bounds are eligible for removal. A
root-owned unrecorded final or temporary candidate is eligible only after 48 hours, which covers a
hard crash during candidate preparation without racing a normal deploy.

Docker cleanup uses one bounded, formatted image inventory and exact `docker image rm` arguments
for stale API, media-worker, web, and backup references. It never uses a broad prune and never
selects the Caddy, storage, node-exporter, or blackbox references. It does not touch containers,
networks, volumes, the current release, a transaction journal, or any protected rollback image.
A Docker inventory or removal failure occurs before release-directory or audit-record deletion and
fails the pass.
Digest pulls are normalized to Docker's actual local identity `repository@sha256:digest` (where
inventory commonly reports `Tag=<none>`); release tags are not fabricated during matching.

Before the first registry pull, every deployment also writes a durable mode-0600 application-ref
record under `/opt/aperture/deploy-attempts`. This bounded root-owned ledger lets GC account for
exact refs pulled by multiple failed or interrupted deployments even when their unaccepted
candidate directories have already been removed. GC deduplicates those refs with accepted-history
refs, protects every application digest used by the current release or either retained
predecessor, and does not try to remove aliases that share those protected digests. After the
bounded Docker inventory and every nonprotected exact removal succeed (or establish that the ref
is absent), the whole attempt is accounted for and its record is removed; shared protected refs
therefore cannot pin ledger capacity. More than 1,000 unconsumed records fails closed before
another attempt receives pull authority.
The pending attempt inode is fully written and fsynced before no-replace publication. A pending
inode without a final record proves publication never returned and pulls never began, so a later
deployment or GC pass can discard it safely; a linked pending/final pair is validated and finalized.

Eligible release-directory removal is also crash-consistent. GC first renames each directory to a
recognized `.gc-removed-*` tombstone under `/opt/aperture/releases` and fsyncs that parent, then
recursively deletes the tombstone. A crash after the rename or during recursive deletion leaves a
committed full or partial tombstone; the next pass validates its ownership, permissions, contents,
and fixed-root location and finishes deletion instead of trying to validate it as an intact
accepted release. A tombstone for a protected release, an unexpected name, a symlink, or a
coexisting canonical directory fails closed.

Root-owned job payloads and deploy-account incoming payloads older than 48 hours are removed only
when they are empty or contain a safe subset of the three expected regular files. Queued or
running jobs are preserved only for the validated active unit; reconciled abandoned jobs are then
eligible for removal. Extra entries, symlinks, unexpected ownership or permissions, and
paths outside their fixed roots fail closed without being followed. The pass records whether free
space was already below 2 GiB, attempts only the safe cleanup above, then fails with `low_disk` if
at least 2 GiB is still unavailable. A failed service is visible to systemd and retries on its
bounded restart schedule; no failure authorizes wider deletion.

## One-time GitHub settings

Create a `production` Environment, restrict it to `main`, and require the accountable release
owner as reviewer. The current repository already uses these repository variables:

```text
APERTURE_REGISTRY_REPOSITORY=ghcr.io/hlkstudios-ui/aperture
APERTURE_WEB_HOSTNAME=apertures.online
APERTURE_STORAGE_HOSTNAME=storage.apertures.online
APERTURE_CDN_HOSTNAME=media.apertures.online
APERTURE_POLICY_REQUIRE_APPROVED=true
APERTURE_CAPTCHA_REQUIRED=false
PRODUCTION_DEPLOY_ENABLED=false
```

When CAPTCHA is enabled, also set the public repository variable
`APERTURE_TURNSTILE_SITE_KEY`. After the first manually accepted eight-image release, set these
four repository variables to that release's exact GHCR `tag@sha256:digest` references:

```text
APERTURE_REUSE_CADDY_IMAGE
APERTURE_REUSE_STORAGE_IMAGE
APERTURE_REUSE_NODE_EXPORTER_IMAGE
APERTURE_REUSE_BLACKBOX_IMAGE
```

Set these non-secret values on the protected `production` Environment:

```text
APERTURE_TAILSCALE_OIDC_CLIENT_ID
APERTURE_TAILSCALE_OIDC_AUDIENCE
APERTURE_TAILSCALE_HOST=aperture-origin.tail9522a4.ts.net
APERTURE_DEPLOY_KNOWN_HOSTS=<the pinned OpenSSH host-key record for that exact MagicDNS name>
APERTURE_DEPLOY_SSH_USER=aperture-deploy
```

Set only this Environment secret:

```text
APERTURE_DEPLOY_SSH_PRIVATE_KEY=<the dedicated deploy key, not an owner/root key>
```

If GHCR packages are private, log the VPS root Docker client into `ghcr.io` once with a separate
read-only package credential. Never put that credential in the runtime dotenv or GitHub workflow.

## Tailscale workload identity

Configure Tailscale Workload Identity Federation for the GitHub OIDC subject:

```text
repo:hlkstudios-ui@199159002/Aperture@1338894782:environment:production
```

Grant it only `auth_keys` capability for `tag:aperture-ci`. Apply and validate
[`tailnet-policy.example.hujson`](../deploy/production/private-studio/tailnet-policy.example.hujson):
the ephemeral CI tag can reach `tag:aperture-studio` only on TCP 22, while the owner can reach
Studio on TCP 443. Tailscale SSH stays disabled; the workflow uses ordinary OpenSSH over the
encrypted tailnet path.

Official setup references:

- [Tailscale GitHub Action](https://tailscale.com/docs/integrations/github/github-action)
- [Tailscale Workload Identity Federation](https://tailscale.com/docs/features/workload-identity-federation)
- [GitHub deployment environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)

## One-time VPS boundary

From a reviewed checkout, generate a dedicated Ed25519 public key and transfer only that public
key plus `install_ci_deploy.sh` and `deploy_release.py` through the existing owner administration
channel. Then run:

```sh
sudo sh deploy/production/hostinger/install_ci_deploy.sh \
  --public-key-file /root/aperture-github-deploy.pub
```

The installer creates a password-locked `aperture-deploy` account with a private primary group and
no supplementary groups, a mode-0700 incoming spool, root-owned job/status directories, a
root-owned controller and bounded mode-0700 attempt ledger, and one exact passwordless sudo
command. It refuses pre-existing account,
home, `.ssh`, `authorized_keys`, or incoming-spool state with unexpected ownership, permissions,
symlinks, shell, password state, or group membership. It does **not** create the launch marker,
shared runtimes, accepted baseline, or transaction journal.
It also installs and enables `aperture-deploy-recovery.service`; it does not start production or
create the condition that activates recovery. Both `--recover` and the transient `--worker` mode
reject sudo provenance and are callable only by host-owned systemd/root execution, not the SSH
deploy account. The installer also enables the condition-gated daily GC timer; its hidden `--gc`
mode has the same host-root-only and sudo-provenance rejection.

The first production launch remains the manual, evidence-gated procedure in
[`deploy/production/hostinger/README.md`](../deploy/production/hostinger/README.md). Register its
reviewed source as one root-owned directory directly under `/opt/aperture/releases/`, place its
mode-0600 public runtime snapshot at `.env`, install the live public and private runtime files as
`/opt/aperture/shared/production.env` and `/opt/aperture/shared/private-studio.env`, and point
`/opt/aperture/current` to that exact release using the normalized relative target
`releases/<baseline-release-id>` (not an absolute symlink). The baseline must contain the same
explicit bundle files and `.aperture-source-sha` contract accepted by `deploy_release.py`.
The extracted allowlist is mode 0644 except for the explicit
`deploy/production/hostinger/operations.sh` executable, which is fchmoded to 0755 before its inode
is fsynced. This preserves the steady-state cron execution contract across a power loss.

Before creating the launch marker, create
`/opt/aperture/release-history/<baseline-release-id>.json` as a root-owned mode-0600 file. Its
`release_id` must equal the basename targeted by `/opt/aperture/current`; `source_commit` must equal
that release's `.aperture-source-sha`; every full reference and digest must equal the corresponding
value in the live `production.env`; and the private runtime's Caddy reference must agree. The exact
record shape is:

```json
{
  "accepted_at": "2026-08-30T00:00:00+00:00",
  "database_schema_rollback": "not_attempted",
  "digests": {
    "api": "sha256:<64 hex>", "media_worker": "sha256:<64 hex>",
    "web": "sha256:<64 hex>", "backup": "sha256:<64 hex>",
    "caddy": "sha256:<64 hex>", "storage": "sha256:<64 hex>",
    "node_exporter": "sha256:<64 hex>", "blackbox": "sha256:<64 hex>"
  },
  "effective_runtime_references": {
    "api": "ghcr.io/hlkstudios-ui/aperture/api:<tag>@sha256:<64 hex>",
    "media_worker": "ghcr.io/hlkstudios-ui/aperture/media-worker:<tag>@sha256:<64 hex>",
    "web": "ghcr.io/hlkstudios-ui/aperture/web:<tag>@sha256:<64 hex>",
    "backup": "ghcr.io/hlkstudios-ui/aperture/backup:<tag>@sha256:<64 hex>",
    "caddy": "ghcr.io/hlkstudios-ui/aperture/caddy:<tag>@sha256:<64 hex>",
    "storage": "ghcr.io/hlkstudios-ui/aperture/storage:<tag>@sha256:<64 hex>",
    "node_exporter": "ghcr.io/hlkstudios-ui/aperture/node-exporter:<tag>@sha256:<64 hex>",
    "blackbox": "ghcr.io/hlkstudios-ui/aperture/blackbox:<tag>@sha256:<64 hex>"
  },
  "platform": "linux/amd64",
  "previous_release": null,
  "release_id": "<baseline-release-id>",
  "schema_version": 1,
  "source_commit": "<40-hex reviewed commit>",
  "status": "accepted"
}
```

Do not substitute tag-only references. Write the completed record to a temporary root-owned file,
set mode 0600, then rename it into `release-history` and fsync that directory. Running
`sudo /usr/local/sbin/aperture-deploy-release --report-current-source-sha` must return the expected
commit before the launch marker is created; any mismatch fails at `accepted_record`.

Only after all launch evidence passes, the public and private stacks are healthy, the off-site
backup/restore rehearsal works, the GHCR platform references above are recorded, and the release
owner approves unattended application deployment, create this root-owned marker with the exact
content:

```text
APERTURE_PRODUCTION_LAUNCH_ENABLED
```

at `/etc/aperture/production-launch-enabled`, then set the repository variable
`PRODUCTION_DEPLOY_ENABLED=true`. Presence alone is insufficient; the controller verifies the
marker content, ownership, permissions, baseline, shared runtimes, and current release.

## Everyday use

For a direct main push:

```sh
git add <reviewed-files>
git commit -m "Describe the Aperture improvement"
git push origin main
```

A pull request is safer because `main` can require the API, web, and deployment-control checks
before merge. After merge, approve the waiting `production` deployment in GitHub. The workflow
then performs the registry publication, transfer, backup, rollout, validation, and recovery steps.

Cloudflare CDN/geo Worker changes are intentionally outside this VPS workflow. Changes to those
edge packages require their separate reviewed deployment and smoke procedure.
