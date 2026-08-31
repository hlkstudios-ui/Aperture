# Production Owner Handoff

This document is the input and evidence contract for moving Aperture from the verified isolated staging topology to production. The owner selected a Hostinger VPS and approved the initial launch with payments disabled; the corresponding non-commercial target is in [`deploy/production/hostinger`](../deploy/production/hostinger/README.md). The approved existing-host target is Hostinger's Boston 2 (`Boston_2`) KVM 4 using the guarded `compact` profile: provider-labeled 16 GiB RAM, 4 vCPU, and 200 GiB disk, with fail-closed guest-visible audit floors of 15 GiB and 190G. The `full` KVM 8 profile (32 GiB, 8 vCPU, 400 GiB; observed floors 31/380) remains the recommended default for new capacity. This document does not contain secrets or turn a staging pass into a launch approval.

For a no-cost public demonstration before production ownership is ready, use [`deploy/staging/free-tier`](../deploy/staging/free-tier/README.md). That profile intentionally sleeps, co-locates workers, limits media size, and offers no Toronto placement, HA, production recovery, content-rights, or legal evidence. It is not a replacement for this handoff contract.

Production remains prohibited until every row below has an accountable owner, supplied input, verification evidence, and approval date. Secrets must be delivered through the chosen deployment platform's secret manager—not committed, pasted into tickets, or written into this document.

## 1. Owner decisions and access

| Required input | Owner must supply | Acceptable completion evidence |
| --- | --- | --- |
| Accountable launch owner | Name/role and launch approval authority | Recorded approval with date and release identifier |
| Production operator | Audited deployment access and incident responsibility | Successful least-privilege login and named on-call escalation |
| Single administrator | Final administrator email and out-of-band identity recovery procedure | Interactive provisioning audit event, MFA enrollment, offline recovery-code custody, and successful recovery-code login |
| Public names | Customer, API, media/CDN, and optional Studio hostnames | Controlled DNS records and public resolution from at least two networks |
| Region and audience | Primary region, allowed territories, data residency constraints, and launch regions | Approved architecture/rights record matching configured delivery boundaries |
| Recovery objectives | Database/media RPO and RTO | Owner-approved numeric objectives and a restore exercise meeting them |

## 2. Runtime and secret contract

The production secret manager must inject these values into the API, media worker, scene worker, migration job, and web image only where required. Use separate identities for application runtime, migration, backup, monitoring, and operators when the provider supports them.

| Variable | Requirement |
| --- | --- |
| `APP_ENV` | Exactly `production` |
| `API_ORIGIN`, `WEB_ORIGIN` | On the API service, the canonical public HTTPS origins; no loopback, internal service name, or shared staging hostname. On the web service only, `API_ORIGIN` is the private server-to-server FastAPI target and must never use a `NEXT_PUBLIC_*` name. |
| `DATABASE_URL` | Isolated production PostgreSQL; TLS and provider backup/failover policy enabled |
| `REDIS_URL` | Isolated production Redis with authentication/TLS and persistence appropriate to queue/session use |
| `S3_ENDPOINT`, `S3_PUBLIC_ENDPOINT`, `S3_REGION`, `S3_BUCKET` | Private production object store and HTTPS browser-facing delivery boundary; never the staging bucket |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | Least-privilege workload credential or provider-equivalent injected identity; no public-list/read permission |
| `SESSION_SECRET` | Environment-specific high-entropy value, at least 32 characters; rotation procedure recorded |
| `SESSION_COOKIE_DOMAIN` | Leave unset in production. The same-origin gateway permits host-only customer and remembered-account cookies; verify no `Domain` attribute plus Secure, HttpOnly, and SameSite in a real browser. |
| `OAUTH_*_CLIENT_ID`, `OAUTH_*_CLIENT_SECRET` | Configure complete pairs only for enabled providers and inject them into the API service only. Register the exact storefront `/api/gateway/auth/oauth/{provider}/callback` HTTPS URL. |
| `CAPTCHA_REQUIRED`, `NEXT_PUBLIC_TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` | When CAPTCHA is enabled, require both keys. The site key is the only public web build/runtime value; the secret is API-only. The web CSP admits only Turnstile's exact script/frame host. |
| `BRAND_AI_PROVIDER`, `BRAND_AI_MODEL`, `BRAND_AI_TIMEOUT_SECONDS`, `BRAND_AI_RATE_LIMIT_PER_HOUR`, `OPENAI_API_KEY` | Keep the assistant disabled until an owner-approved, API-only OpenAI project key is installed. Record the tested model, project owner, retention setting, rotation/revocation procedure, spend cap and alerts, then perform one non-sensitive owner-only smoke request. Disable by setting the provider to `disabled` and restarting the API; revoke the key for emergency containment. |
| `PRIVATE_STUDIO_REQUIRED`, `ADMIN_WEB_ORIGIN`, `STUDIO_EDGE_SECRET` | Exactly `true`, the private Tailscale HTTPS origin, and a separate 48+ character edge secret shared only by App Platform and the private gateway. Administrator cookies remain host-only. |
| `MEDIA_DELIVERY_MODE`, `CDN_PUBLIC_ORIGIN`, `MEDIA_SOURCE_ORIGINS` | Exactly `cdn` and the approved HTTPS media hostname in production; the web value is a server-side CSP allowlist, not a browser API endpoint |
| `CDN_SIGNING_SECRET`, `CDN_ORIGIN_SECRET`, `CDN_TOKEN_TTL_SECONDS` | Separate high-entropy edge-grant/origin secrets and the matching bounded lifetime (300 seconds in the supplied target); signing secrets never enter the web image |
| `GEO_ASSERTION_SECRET`, `ORIGIN_EDGE_SECRET`, `GEO_EDGE_ORIGIN_WEB` | Separate high-entropy geo-signing and origin-admission secrets shared only with the trusted edge, plus the direct Hostinger origin hostname; never point the edge origin at the public hostname |
| `MALWARE_SCANNER_MODE`, `MALWARE_SCANNER_HOST`, `MALWARE_SCANNER_PORT`, `MALWARE_SCANNER_TIMEOUT_SECONDS` | Production requires `clamav_tcp` and a network-restricted current-definition clamd endpoint reachable only by upload/API workloads. Preserve update/health ownership and never expose port 3310 publicly. |
| `FEATURE_SCENE_LENS_ENABLED`, `FEATURE_ASK_MOVIE_ENABLED`, `FEATURE_COMMUNITY_ENABLED`, `FEATURE_WATCH_PARTIES_ENABLED`, `FEATURE_EXPERIMENTAL_RECOMMENDATIONS_ENABLED` | Explicit launch decisions for risky optional domains. A change requires an API restart; disabled customer routes fail closed with 404. Ask requires SceneLens, and watch parties require Community, so parent flags take precedence. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_STARTTLS` | Approved production transactional-email service with SPF/DKIM/DMARC and reset-delivery acceptance |
| `BILLING_PROVIDER` | Exactly `disabled` for the approved initial non-commercial launch. Checkout, portal, payout, and webhook surfaces must fail closed, and Stripe credentials remain empty. A later paid launch requires a separate reviewed release with `stripe`, live credentials, signed-webhook and lifecycle acceptance, and updated policy approval. |
| `ERROR_TRACKING_DSN` | Production error project with default PII collection disabled and retention/access approved |
| `METRICS_BEARER_TOKEN` | High-entropy monitoring-only secret, delivered only to the scraper and API |
| Alert thresholds | Owner-approved queue backlog, queued age, and processing failure thresholds based on provisioned capacity |

Application startup already rejects placeholder production credentials, HTTP public origins, missing SMTP, the development billing stub, unknown billing modes, weak monitoring tokens, and a missing error-tracking DSN. A successful startup is necessary but not sufficient evidence.

## 3. Infrastructure acceptance

The chosen provider must supply evidence for all of the following:

- Eight immutable web/API/media-worker/backup/Caddy/storage/node-exporter/Blackbox artifacts identified by digest; the API/scene/operations image is
  FFmpeg-free, the media worker has a distinct audited FFmpeg image, and both Python images have
  retained vulnerability-scan evidence. The first-party Caddy and storage artifacts must retain
  source/version identity and vulnerability reports. The first-party exporter artifacts must
  retain the same evidence; no manual production file editing.
- A one-shot, release-ordered Alembic migration job with a recorded migration head.
- Independently supervised API, media worker, and scene worker processes.
- Database, Redis, and object-storage network isolation; no public database/Redis endpoint.
- Private, versioned media storage with encryption, lifecycle policy, replication/durability class, and denied anonymous access.
- A private malware-scanning service with current signed definitions, monitored update failures, bounded stream/timeout behavior, and clean/detected/unavailable control-file acceptance. Scanner outage must leave masters quarantined.
- Publicly trusted TLS, HSTS, narrow CORS, and the configured web/API cookie boundary.
- A Tailscale-only Studio gateway following [`deploy/production/private-studio`](../deploy/production/private-studio/README.md); public and direct-origin Studio/admin paths must return 404.
- CDN/origin behavior that preserves authenticated media authorization, byte ranges, content types, cache policy, and token expiry. Raw masters must never be public.
- Geo-aware public ingress that strips client assertions, signs the provider-derived ISO country, fails closed when country is unavailable, and forwards the storefront to the direct Hostinger origin. FastAPI ingress is allowlisted to readiness, the signed billing webhook, and the protected CDN origin; browser API traffic uses the same-origin web gateway. Prove spoofed, missing, allowed, and denied countries without exposing either secret.
- Health/readiness probes, controlled rollout, capacity limits, autoscaling or documented fixed capacity, and resource budgets for FFmpeg workers.
- Central structured logs with request IDs and access controls that prevent secret, cookie, signed-URL, media-key, and customer-question leakage.

Attach provider resource identifiers and policy/version references, but never secret values.

## 4. Backup, restore, and rollback evidence

Before traffic:

1. Schedule encrypted PostgreSQL backups to an off-site or provider-isolated retention boundary.
2. Configure media versioning plus the approved replication/durability strategy.
3. Back up non-secret deployment configuration and record secret-recovery ownership separately.
4. Restore a production-shaped snapshot into a new isolated environment; verify checksums, migration head, table count, representative customer/catalog relations, and private media playback.
5. Record measured RPO/RTO and compare them with the owner-approved objectives.
6. Deploy a known-good release, roll forward once, shift test traffic, roll back application traffic through the real controller, and verify health, authentication, catalog, upload, processing, playback, Studio, logs, and alerts.

Use [the Hostinger backup and recovery procedure](../deploy/production/hostinger/README.md) for the provider rehearsal. The staging procedure remains a behavioral reference, not a production scheduler or storage policy. Follow [the incident runbooks](RUNBOOKS.md) during rehearsal.

For CI-managed Hostinger production, recover an already active bad application release by creating
a reviewed Git revert commit and pushing or merging it through the normal protected workflow. The
controller builds a new immutable candidate, preserves the accepted Caddy/storage/exporter
digests, backs up first, and runs preflight, Caddy coupling, public smoke, and compensation. Do not
manually repoint `/opt/aperture/current`, edit the shared runtimes, or invoke the legacy rollback
program after the controller layout exists. Retain the previous release directory and exact
eight-artifact evidence for recovery and audit; the Scene worker continues to bind to the accepted
API digest. Application rollback never rolls back database data, so migration compatibility still
requires explicit review.

## 5. Monitoring and incident acceptance

- Connect `/metrics` through an authenticated private scrape path.
- Install [the repository alert rules](../ops/prometheus-alerts.yml) in the selected monitoring system and connect real receivers.
- Supply primary/secondary on-call routes and escalation timers.
- Send a synthetic error and confirm it reaches the production error project without PII.
- Trigger a safe synthetic readiness failure and one queue/storage threshold in an isolated production-like exercise; confirm receipt, acknowledgement, and resolution.
- Verify external uptime probes from at least two regions and preserve request IDs through the edge.
- Run tabletop exercises for database outage, storage outage, queue backlog, CDN/origin fault, administrator lockout, failed media, and bad deployment.

Repository rules and dashboards without a receiver do not satisfy this gate.

## 6. Content, rights, and policy package

For every launch title, the owner must supply an authoritative record containing:

- content identifier and authorized source;
- licensor and evidence/reference location;
- allowed territories;
- start/end window and timezone basis;
- permitted cuts/editions, audio, subtitles, artwork, stills, trailers, and derived thumbnails;
- scene/transcript/production-note evidence and permitted use when SceneLens/Cinephile features are enabled;
- takedown/contact owner and expiry/removal procedure.

Counsel or the accountable policy owner must approve the applicable privacy notice, terms, copyright/takedown process, cookie/analytics disclosure, accessibility statement/process, community rules, subscription/cancellation/refund terms, and data-request procedure. Policy routes and consent behavior must be implemented and acceptance-tested from the approved final text; placeholders are not acceptable.

Replace the eight labeled entries in [`apps/web/content/policies.json`](../apps/web/content/policies.json)
with the final approved version, effective UTC timestamp, approver role, and structured text.
Only then set `POLICY_REQUIRE_APPROVED=true` in the labeled Hostinger owner input. The
web build and deploy renderer both fail closed before that point. Do not set the flag merely
to make a build pass; preserve the approval reference in the launch-evidence record and
browser-test every published route from the production edge.

## 7. Production acceptance record

Record evidence—not just a checkbox—for:

- production administrator login, MFA, recovery, and sign-out;
- customer registration and SMTP password reset;
- licensed title creation, metadata/artwork, upload, checksum, processing, adaptive renditions, subtitles/audio, preview, scheduling/publishing, and intended homepage rail;
- customer search/detail/play/leave/resume, Continue Watching, My List, rating, recommendations/Taste DNA, SceneLens spoiler boundary, Passport, and real analytics;
- portable customer export and confirmed deletion against an approved disposable production test account;
- authorized storage delivery with no anonymous master/object access;
- monitoring notification, backup restore, and traffic rollback;
- browser matrix and accessibility checks against the public production edge;
- a second clean-deployment repetition using new isolated fixtures.

The final production launch record must reference the release/image digests, migration head, infrastructure version, test artifacts, unresolved-risk register, approvers, and timestamp. Only then may [the launch checklist](LAUNCH_CHECKLIST.md) reduce its six blockers to zero.

Use [`deploy/production/launch-evidence.example.json`](../deploy/production/launch-evidence.example.json)
and its fail-closed verifier to assemble the secret-free machine-readable portion of this
record. `evidence_complete` means only that every required evidence class is represented and
structurally bound to the release; it never substitutes for inspecting the referenced
artifacts or for the accountable human launch approval.

Use [the read-only production preflight](../deploy/production/README.md) after secret injection and migration. A green preflight is one infrastructure artifact, not a substitute for the rest of this acceptance record.

## Owner response template

Return the following without secrets:

```text
Launch owner / operator:
Chosen hosting and region:
Customer / API / media hostnames:
Database / Redis / object-storage provider and resource references:
Deployment controller:
Secret-manager reference:
Backup retention, replication, RPO, RTO:
Monitoring, error tracking, alert receiver, on-call owner:
Production administrator email and recovery custodian:
Billing scope/provider (or explicit no-paid-launch decision):
Licensed catalog/rights package reference:
Approved policy package reference:
Target launch window:
```
