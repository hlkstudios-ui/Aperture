# Production deployment boundary

The active hosting target is now the [Hostinger VPS package](hostinger/README.md). The
older DigitalOcean package is retained only for migration history.

Production infrastructure is intentionally provider-neutral and is not instantiated by this repository. The owner must first supply the resources and approvals in [`docs/PRODUCTION_HANDOFF.md`](../../docs/PRODUCTION_HANDOFF.md).

The API release image contains `scripts/production_preflight.py`. Run it with secrets injected by the deployment platform; do not create or copy a plaintext production env file.

Recommended release order:

1. Resolve immutable web/API/worker image digests.
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
- Stripe accepts a read-only authenticated account lookup; no Checkout, charge, customer,
  subscription, or webhook mutation is performed by preflight.
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
`production`, bind the exact release, four image digests, migration head, infrastructure
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
web and API bases. It checks TLS validation, required security headers, request-ID
propagation, dependency readiness, fail-closed protected surfaces, and hidden production
API documentation without creating accounts or changing state:

```bash
SMOKE_WEB_ORIGIN=https://watch.example.com \
SMOKE_API_ORIGIN=https://watch.example.com/api \
python3 deploy/production/public_edge_smoke.py --environment production
```

Do not set `SMOKE_CA_FILE` in production; successful verification must use the operating
system's publicly trusted certificate roots. This smoke is safe to repeat but does not
replace authenticated browser, playback, upload, billing, email, or rollback acceptance.
