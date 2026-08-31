# DigitalOcean Toronto production target

This target uses App Platform in `tor`, Managed PostgreSQL and Valkey in `tor1`, and a
private, versioned Standard Space in `tor1`. The app spec is a credential-free template;
do not apply it directly or commit a rendered copy.

Production Studio is deliberately absent from the public edge. Deploy the separate
[`private-studio`](../private-studio/README.md) Tailscale gateway and inject the matching
`ADMIN_WEB_ORIGIN` and `STUDIO_EDGE_SECRET`. App Platform and FastAPI both fail closed with
404 when that gateway assertion is missing, including on the direct provider hostname.

## Dummy configuration now

The repository-root `.env` is the only owner-edited credential file. Add the labeled
DigitalOcean inputs there when needed. `credentials.example.env` is the permanent,
non-secret validation fixture and reference; it must remain free of real credentials.

Configure both values for every OAuth provider you enable and register the storefront
`/api/gateway/auth/oauth/{provider}/callback` URLs. With `CAPTCHA_REQUIRED=true`, the renderer
requires both Turnstile halves. Only `NEXT_PUBLIC_TURNSTILE_SITE_KEY` enters the web component;
the Turnstile secret and all OAuth credentials enter the API component. Customer cookies are
host-only through the same-origin gateway, so the spec deliberately omits
`SESSION_COOKIE_DOMAIN`.

Render the safe dummy files without making network calls:

```bash
python deploy/production/digitalocean/render_config.py \
  --input deploy/production/digitalocean/credentials.example.env --mode dummy
```

This creates a mode-0600 `app.local.yaml`, which is git-ignored. Dummy mode only proves deterministic substitution and YAML structure. It is
not deployable and does not claim that fake services exist.

## Provision once

1. Create production PostgreSQL 17 and Valkey 8 clusters in `tor1`, with trusted sources
   restricted to the App Platform VPC. Record their cluster names.
   Provision a ClamAV-compatible clamd service on a private network reachable by the API
   workloads, with no public port, monitored signed-definition updates, and capacity for the
   configured maximum master size. Record its private hostname and port in the labeled
   credential input; the supplied App Platform spec deliberately does not pretend this
   separately operated security service exists.
2. Create a Standard Space in `tor1`. Enable versioning, set its bucket ACL/file listing
   to private, keep every object private, leave the bucket policy absent unless an audited
   non-public workload policy is required, and create a bucket-scoped workload key. Do
   not apply a blanket `Deny` to `Principal: *`; it would also deny authenticated workers.
   Browser uploads use short-lived signed path-style URLs against the regional Space
   origin (`tor1.digitaloceanspaces.com`). Raw masters and playback outputs remain
   private. Deploy the protected edge adjunct in `../cdn` for playback; the API remains
   the secret, rights-revalidating origin.
3. Configure the DNS zone and choose one customer hostname. Deploy the trusted geo ingress
   in `deploy/production/geo-edge`, set its `ORIGIN_WEB` to the assigned direct App Platform
   origin, and route the customer hostname through it. Browser API calls use Next's
   same-origin `/api/gateway`; the web service reaches FastAPI through App Platform's private
   `http://api:8000` service address.
   App Platform exposes FastAPI directly only for the Stripe webhook, protected media origin,
   and readiness probe. All other `/api/*` paths fall through to the web service and return
   404. This does not depend on the deprecated per-component `routes` field.
4. Fill every required DigitalOcean label in the repository-root `.env`, then run
   `python deploy/production/digitalocean/render_config.py --mode deploy`. Deploy mode
   fails closed on any dummy marker, Stripe test key, malformed signing-secret prefix, or
   short application secret. DigitalOcean database bindables remain literal.
5. Validate with `doctl apps spec validate deploy/production/digitalocean/app.local.yaml`,
   review the estimate, then enter the values marked `SECRET` through App Platform's
   encrypted-variable UI. Apply only after comparing the final platform spec with the
   local rendered file; remove the local rendered files after deployment.
6. Deploy `deploy/production/cdn` on the media hostname with the same signing and origin
   secrets supplied to the API. Keep `TOKEN_TTL_SECONDS=300`, point `ORIGIN_API` at the
   allowlisted public `/api` media origin, and run the CDN acceptance in its README. DigitalOcean Spaces
   presigned URLs are deliberately not used as the playback CDN path because the provider
   documents that presigned requests bypass CDN caching.

The target includes a five-minute UTC scheduled maintenance job. It materializes due
catalog publication/archive transitions without relying on customer traffic and removes
expired raw analytics in bounded batches while retaining anonymous aggregates.

Every release runs Alembic as a blocking pre-deploy job and the full secret-safe
dependency preflight as a post-deploy job. The latter verifies the exact migration head,
PostgreSQL, Valkey, private/versioned Spaces, SMTP authentication without sending, and a
read-only Stripe account lookup. Its failure prevents the release from being accepted;
public DNS/browser/rollback/backup/alert/content gates still require separate evidence.

Once DNS and the App Platform domain are active, run the parent production public-edge
smoke with `SMOKE_WEB_ORIGIN=https://<WEB_HOSTNAME>`. The smoke verifies the same-origin
gateway and its private cache policy, TLS and security headers, readiness, request-ID
propagation, and that non-allowlisted direct API paths return 404.

A separate PostgreSQL 17 backup image runs daily at 03:17 UTC. It uses only the private
database bindable and a backup-only Spaces identity, creates a custom-format dump without
owners/ACLs, records SHA-256, migration head, table count, size and UTC time in a private
manifest, and never puts the database password in process arguments. Configure the backup
Space as private and versioned with lifecycle retention matching `BACKUP_RETENTION_DAYS`.
The scheduled job is implementation evidence only: launch still requires a successful
isolated restore and measured RPO/RTO against the labeled owner targets.

For the production rehearsal, use `restore.example.env` as a non-secret label reference
and fill the matching restore labels in the repository-root `.env`. Create a new empty
PostgreSQL database whose name begins with `aperture_restore_`, and use a read-only key
for the backup Space. Run the verifier from the backup image so PostgreSQL client versions
match:

```bash
docker run --rm --env-file .env \
  aperture-backup:production-readiness \
  /opt/aperture-backup/bin/python /app/production_restore_verify.py
```

The verifier requires the exact confirmation phrase in the example file, refuses any
other database-name prefix or non-empty target, binds the manifest to its dump object,
checks size and SHA-256 before `pg_restore`, and verifies migration head and public-table
count afterward. It never creates or drops a database. Record its JSON result and elapsed
time in the owner acceptance record, then have an authorized operator remove the isolated
database through the provider console.

## Traffic rollback rehearsal

Use `rollback.example.env` as a non-secret label reference, put the matching labels in the
repository-root `.env`, use a short-lived least-privilege operator token, and explicitly
select a previously successful deployment.
The rollback tool reads only its allowlisted labels without evaluating the dotenv file as
shell code; explicitly supplied process variables take precedence. Inspecting the target is
read-only:

```bash
python3 deploy/production/digitalocean/digitalocean_rollback.py --input .env --mode inspect
```

Execution calls App Platform's rollback endpoint only after the target inspection passes
and the exact confirmation phrase is present:

```bash
python3 deploy/production/digitalocean/digitalocean_rollback.py --input .env --mode execute
```

The script returns only stable JSON evidence and never provider error bodies or token
values. Revoke the token afterward. App Platform rollback duplicates the selected
deployment's code, configuration, and app spec; it does not roll back database data.
Therefore, confirm migration backward compatibility before execution, then wait for the
returned rollback deployment and run readiness plus the complete acceptance subset in the
bad-deployment runbook. The script initiates the rollback; initiation alone is not proof
that traffic became healthy.

## Stripe test-mode acceptance

Use `BILLING_PROVIDER=stripe`, an `sk_test_...` key, and a test-mode webhook signing
secret outside production. Register `/api/billing/stripe/webhook` for
`customer.subscription.created`, `customer.subscription.updated`, and
`customer.subscription.deleted`. Checkout and webhook tests must use Stripe test mode;
the repository unit tests use fake credentials and make no network call.

Production validation deliberately requires an `sk_live_...` key. Add it only at the end
through DigitalOcean's encrypted variable UI, rotate the webhook endpoint to live mode,
and repeat checkout, renewal, payment-failure, cancellation, and idempotent webhook
acceptance with an approved disposable account.

Before promotion, run the migration and the read-only preflight described in the parent
directory. For Spaces, preflight accepts a private ACL with no bucket policy or a policy
that contains no anonymous allow; any public ACL or anonymous allow fails closed.
