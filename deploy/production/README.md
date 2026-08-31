# Production deployment boundary

The active hosting target is now the [Hostinger VPS package](hostinger/README.md). The
older DigitalOcean package is retained only for migration history.

Production infrastructure is intentionally provider-neutral and is not instantiated by this repository. The owner must first supply the resources and approvals in [`docs/PRODUCTION_HANDOFF.md`](../../docs/PRODUCTION_HANDOFF.md).

The API release image contains `scripts/production_preflight.py`. Run it with secrets injected by the deployment platform; do not create or copy a plaintext production env file.

Recommended release order:

1. Resolve the eight immutable Hostinger artifact digests: web, API, media worker, backup, Caddy,
   storage, node exporter, and Blackbox. Bind the Scene worker to the API digest.
2. Run the API image with `python scripts/production_preflight.py --configuration-only`. This verifies that the effective settings pass the application's production validation without contacting dependencies.
3. Run `alembic upgrade head` as the one-shot migration identity.
4. Run `python scripts/production_preflight.py` as a read-only validation identity.
5. Start workers and API, wait for `/ready`, then start/shift traffic to the web edge.
6. Run production-safe smoke and acceptance using approved disposable accounts/content.
7. Observe one complete alert window before promotion is final.

The full preflight fails unless:

- PostgreSQL is reachable at the single Alembic head;
- Redis accepts an authenticated ping;
- object storage is reachable, versioning is enabled, ACLs are private, and the provider can prove that no bucket policy grants anonymous read/list access;
- SMTP TLS/authentication succeeds without sending a message.
- Billing either reports the explicitly approved `payments_intentionally_disabled` state without
  contacting Stripe, or Stripe accepts a read-only authenticated account lookup. Preflight never
  creates a Checkout, charge, customer, subscription, or webhook mutation.
- the private ClamAV-compatible endpoint accepts a clamd PING; no object is submitted or
  mutated by preflight.

Output contains only stable check names/codes and never exception text, endpoints, usernames, passwords, tokens, or object keys. DigitalOcean Spaces is handled explicitly: when AWS's policy-status operation is unavailable, a private ACL plus no bucket policy passes, a present policy is parsed conservatively, and any anonymous read/list allow fails. Other providers without verifiable policy evidence fail with `public_policy_state_unverifiable`.

The preflight does not replace public DNS/TLS checks, CDN authorization tests, actual reset-email delivery, error/alert delivery, backup restore, traffic rollback, browser acceptance, content-rights review, or launch approval.

## Secret-free launch evidence record

Validate the labeled dummy record without contacting any provider:

```bash
python3 deploy/production/launch_evidence.py --mode dummy \
  --record deploy/production/launch-evidence.example.json
```

It must report `no_go` with all six gates remaining. When production evidence exists, copy
the example to the git-ignored `launch-evidence.local.json`, change `environment` to
`production`, bind the exact release and all nine component image-digest bindings (the Hostinger
Scene worker reuses the API digest, so its nine bindings represent eight built artifacts), migration head, infrastructure
version, owners, approvals, and evidence references, then run:

```bash
python3 deploy/production/launch_evidence.py --mode verify \
  --record deploy/production/launch-evidence.local.json
```

Verification fails closed on missing evidence classes, unexpected gates, dummy markers,
likely secrets, malformed image digests, a different migration head, naive/future
timestamps, or a record that claims its own final approval. Even a complete record reports
`human_approval_required: true`; it cannot authorize launch. Store only stable evidence
references in the JSON—never credentials, signed URLs, session identifiers, recovery codes,
or provider tokens.

After the public edge exists, run the credential-free smoke verifier with the exact HTTPS
storefront origin. It checks TLS validation, required security headers, request-ID
propagation, dependency readiness, the private/no-store same-origin gateway contract,
closed direct API paths, and hidden production API documentation without creating accounts
or changing state:

```bash
SMOKE_WEB_ORIGIN=https://watch.example.com \
python3 deploy/production/public_edge_smoke.py --environment production
```

Do not set `SMOKE_CA_FILE` in production; successful verification must use the operating
system's publicly trusted certificate roots. This smoke is safe to repeat but does not
replace authenticated browser, playback, upload, billing, email, or rollback acceptance.
