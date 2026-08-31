# Production Launch Checklist

Last audited: 2026-08-30
Decision: **NO-GO — unresolved critical blockers: 6 external**

`PASS` means the repository and isolated staging evidence are complete. `BLOCKED` means production launch requires missing implementation, owner-supplied configuration, infrastructure, content, or legal approval. A passing staging build is not represented as a production launch.

A separate no-cost public demo target now exists at `deploy/staging/free-tier`. Its sleeping services, shared API/worker process, free quotas, demo-only media, and lack of production SLA/recovery evidence make it staging evidence only; it does not change this checklist's NO-GO decision or blocker count.

## Product

- PASS — Core registration, authentication, profiles, browse, search, detail, playback, resume, account, community, curation, clubs, recommendations, Passport, and Studio journeys pass in isolated HTTPS staging.
- PASS — Automated empty, unavailable, validation, not-found, failed-request, billing-unavailable, and protected-route states are covered without fabricated success.
- PASS — Studio Users provides customer search/detail, portable privacy-safe JSON export, audited reason-gated activate/deactivate, global session revocation, profile/device/subscription/entitlement troubleshooting, and confirmed irreversible deletion requiring the exact email, exact phrase, reason, and authorization reference. Deletion retains only a non-identifying audit tombstone.
- PASS — Studio Subscriptions provides provider-authoritative read-only billing visibility without fabricating provider mutations; Studio Storage exposes registered inventory, object-store availability/versioning, asset states, and recent failures without credentials or object keys.

## Media

- PASS — Browser upload → signed object-store PUT → checksum verification → Redis queue → FFmpeg processing → validated HLS → assignment → protected playback is proven.
- PASS — Generated original fixtures prove AAC audio plus two embedded subtitle tracks, customer language/caption preferences, and protected WebVTT delivery.
- PASS — Three adaptive renditions, Auto/manual selection, range delivery, seek, leave/resume, progress completion, and QoE reporting pass in Chromium, Firefox, and WebKit.
- PASS — SceneLens ingestion, provenance, enrichment, search, publication, timestamp protection, player UI, and reliable-unavailable behavior are proven in the same live-media journey.

## Admin

- PASS — There is no public administrator registration; offline provisioning, server-side authorization, audited login, secure sessions, and rate limiting are active.
- PASS — Studio upload, processing, assignment, catalog edit, preview, publish/unpublish, UTC scheduling/rights windows, homepage draft/preview/publication, moderation, analytics, and operations are working UI paths.
- PASS — Failed jobs expose bounded errors and an audited retry path; incident procedures cover processing, dependencies, queue, origin, lockout, and bad deployments.
- PASS — Studio now provides interactive TOTP enrollment, one-time recovery-code presentation, MFA login/recovery, and explicit sign-out on desktop and mobile.
- BLOCKED — The production administrator has not been provisioned in a production database and MFA has not been enrolled under owner-controlled recovery storage.

## Security

- PASS — Repository secrets are externalized; staging generates isolated mode-0600 random credentials and does not use production data.
- PASS — Staging HTTPS, secure/domain-scoped cookies, HSTS production behavior, narrow CORS, trusted-origin mutation checks, CSP, no-sniff/referrer/frame protections, and disabled production API docs are tested.
- PASS — Customer/admin authorization, session hashing/revocation, profile isolation, upload validation, request limits, and no public admin creation are tested.
- PASS — Uploads use short-lived signed URLs. Playback manifests, subtitles, stills, and segments remain private behind an opaque authenticated authorization proxy with rights/profile/source checks; the master is never public.
- PASS — Large uploads use resumable 16 MiB multipart sessions with server-authoritative part discovery/completion, pause/reselection resume, safe abort, and unchanged full-object integrity validation.
- PASS — Protected CDN delivery is implemented with short-lived HMAC grants, pre-cache validation, secret rights-revalidating origin access, immutable cache keys, private masters, CORS/CSP, content types, and range bypass.
- PASS LOCALLY — Trusted geo ingress strips spoofed assertions, signs Cloudflare-derived viewer country, preserves the request path, and fails closed on unknown country or missing configuration. Real Worker routing, Hostinger origin binding, DNS, and multi-country public acceptance remain external evidence.
- PASS — Simultaneous-stream entitlements are enforced through atomic expiring per-device leases. Admission, refresh, stale recovery, invalid-entitlement fallback, inactive media denial, CDN-token lifetime coverage, and an actionable customer limit state are tested; provider Valkey/CDN drills remain external evidence.
- PASS — Uploaded masters remain non-processable until a persisted malware verdict is clean. EICAR detection, scanner outage quarantine/retry, ClamAV protocol framing, and scanner preflight are automated without weakening checksum/container validation.
- BLOCKED — The Hostinger VPS and Cloudflare zone now exist, but the public production stack and routes remain unopened. Public origin DNS/TLS, the isolated production database/Redis/storage runtime, IAM/encryption evidence, and CDN/origin acceptance have not been supplied and verified end to end.
- PASS — The credential-free public-edge verifier passed six read-only checks against isolated staging HTTPS and is configured for the Hostinger Caddy single-host `/api` ingress contract.

## Data

- PASS — Alembic reaches `b7e4c91d2a60 (head)`, drift checks pass, and destructive migration round trips were exercised during their phases.
- PASS — `deploy/staging/backup.sh` creates a PostgreSQL custom-format dump, non-secret configuration archive, and SHA-256 manifest.
- PASS — `deploy/staging/restore-test.sh` restored the current staging snapshot into a separately named database and verified migration head plus all 91 public tables before safe cleanup.
- PASS — Raw analytics retention is bounded and deletion workflows cascade identifying customer records while retaining non-identifying aggregates/audit tombstones where designed.
- PASS — Optional profile analytics default off, require explicit consent, stop at ingestion when disabled, and delete retained raw profile events on withdrawal. No Algorithm prevents activity-derived Discover ranking while retaining transparent editorial/anonymous aggregate discovery.
- PASS — The staging media bucket has object versioning enabled and public anonymous access disabled.
- PASS LOCALLY — The Hostinger target wires a daily non-root PostgreSQL custom-format backup to an independently credentialed S3-compatible destination, with checksum/migration/table-count manifest and credential-redacted logging; provider execution remains unverified.
- PASS — A current-schema isolated staging backup/restore passed at migration `b7e4c91d2a60` with 91/91 public tables and safe cleanup. The production-format verifier separately proves manifest/object binding, size, SHA-256, empty-target enforcement, migration/table parity, and safe target naming; provider execution remains blocked.
- BLOCKED — That production backup has not been instantiated; off-site retention, restore credentials, object-storage replication/durability class, a successful isolated restore, and measured recovery-point/recovery-time objectives are not verified on the provider.

## Operations

- PASS — Correlated structured API/worker logs, protected Prometheus metrics, readiness, queue/storage/transcode/API/QoE measures, Studio Operations, alert rules, and seven incident runbooks exist.
- PASS LOCALLY — The Hostinger target runs private Prometheus and Node Exporter with bounded retention and no host ports; authenticated API/host metrics plus host-audit, maintenance, backup, and media-replication freshness rules are wired. Secret-safe monitoring rendering and atomic success evidence are tested.
- PASS LOCALLY — Private Blackbox Exporter probes the public web security-header contract, API readiness body, storage readiness, CDN TLS reachability, direct-origin 404 denial, and certificate lifetime. Structural coverage is tested; live DNS/TLS and two-region probes remain external.
- PASS LOCALLY — The first-party Caddy 2.11.4 image passes an executable runtime gate against staging upstreams: missing origin credentials fail with 404, trusted homepage/API traffic passes, public Studio/admin traffic fails with 404, and two-secret private requests reach the web/API applications. The same ordered edge blocks the five advisory-related MinIO request classes before proxying while preserving signed S3 operations. The hardened candidate also runs as the loopback-only private Studio gateway behind tailnet-only Tailscale Serve.
- PASS — Images, one-shot migrations, dependency health checks, staging verification, and bad-deployment procedures are repeatable. The eight-artifact publisher now requires clean committed source, atomically reserves each release ID, proves all tags absent, emits provenance/SBOM attestations, commits a secret-free manifest before pinning, and rejects partial/reused releases. Stateful storage rollback requires compatibility/snapshot/clone evidence, and Caddy rollback or compensation synchronizes and verifies both public and private gateways.
- BLOCKED — The existing Hostinger Boston 2 KVM 4 VPS has been reinstalled and hardened under the guarded `compact` profile. Its private Studio node is tagged, restricted by an owner-only TCP 443 tailnet grant, and configured with non-expiring node credentials, but owner-device Studio/MFA acceptance, the complete eight-artifact registry release, and a real immutable-image traffic rollback have not been completed.
- BLOCKED — `ERROR_TRACKING_DSN` and external alert receivers/on-call routing are not configured; repository rules alone cannot notify an operator.

## Legal / Content

- PASS — Repository/staging media and metadata are generated original fixtures; no commercial movie is bundled.
- PASS — Movie, series, edition, artwork, and scene-evidence rights windows/bases are modeled and enforced at customer delivery boundaries.
- PASS — Eight required policy routes and the global footer publish only owner-approved versions; pending/unknown documents return 404, and production build/deploy gates reject placeholder or incomplete content.
- BLOCKED — The owner has not supplied a licensed production catalog, title-by-title distribution evidence/territories/windows, or legal approval for privacy, terms, copyright/takedown, cookies, accessibility, and subscription/refund policies as applicable.

## Browser Matrix Evidence

- PASS — Common mobile: Pixel 7 Chromium.
- PASS — Tablet: iPad Pro 11 viewport under Chromium; the audit fixed a real 834 px header overlap.
- PASS — Laptop: Desktop Chrome profile.
- PASS — Large desktop: Chromium at 1920 × 1080.
- PASS — Desktop Firefox 153 engine.
- PASS — WebKit 26.5 / Safari-compatible engine, including macOS Option+Tab link-focus behavior.
- PASS — Generated adaptive player acceptance passes in Chromium desktop/mobile, Firefox, and WebKit. Engine-specific navigation/media cancellations are ignored only when they match the browser's documented abort shape; functional and API assertions still must pass.

## Latest Evidence

- Current source validation — PASS: 287 API tests; 369 web tests across 52 files; web TypeScript and ESLint; 142 Hostinger tests plus 12 subtests; 11 private-Studio tests; 8 production-boundary tests; 8 DigitalOcean tests; 6 free-tier staging tests; 10 Cloudflare Worker tests; deployment Ruff, shell syntax, Compose rendering, and diff checks.
- `deploy/staging/verify.sh` plus the current full deployed matrix — PASS, 46/46 enabled-feature Chromium desktop/mobile tests over HTTPS plus 4/4 in the separately rebuilt all-risky-features-off mode, including consent withdrawal/erasure, portable customer export/deletion, Studio Users/Subscriptions/Storage, SMTP reset, and exact subscription entitlements.
- Cross-browser representative product/accessibility matrix — PASS, 24/24 after tablet and WebKit fixes.
- Firefox generated adaptive player — PASS.
- WebKit generated adaptive player — PASS.
- Staging isolated database restore — PASS at `b7e4c91d2a60`, 91/91 public tables present, after applying the privacy, malware, and territory-rights migrations to the integrated stack.
- API integration — PASS, 86/86, including simultaneous-stream lease admission/refresh/expiry, mocked billing/webhooks, production preflight, provider object-storage policy paths, multipart interruption/resume/integrity/malware quarantine, feature-flag fail-closed behavior, launch-evidence validation, maintenance, backup/restore and rollback safety, public-edge verification, worker lease recovery, administrator support authorization, safe export/deletion, bounded homepage queries, and all prior regressions.
- Current-schema staging matrix — PASS, 46/46 enabled-feature Chromium desktop/mobile journeys plus a separate 4/4 all-risky-features-off deployed matrix. This includes the complete consent grant/ingest/withdraw/erase/deny lifecycle, public-endpoint multipart interruption/resume, customer feature-route authorization, and hydration-clean upload scan status.
- Web TypeScript, ESLint with no errors, 15 Vitest checks, and the 45-page production build — PASS. Focused desktop/mobile homepage, Studio-boundary, console/network, and loading-budget browser acceptance passes 6/6 after the Hostinger audit fixes.
- High-traffic homepage/Instant Results poster delivery — PASS LOCALLY. Responsive 185/342/500 px TMDB CDN candidates, lazy decoding, intrinsic dimensions, and desktop/mobile loading budgets are browser-verified without routing artwork through the Hostinger VPS.
- Customer artwork delivery — PASS LOCALLY. Search, activity, global results, movie/series detail, episode stills, cards, and backdrops use source-appropriate responsive candidates and loading priority; owner/private origins are not rewritten. ESLint has zero image warnings, transformation/privacy tests pass, and desktop/mobile catalog plus loading-budget journeys are green.

## Launch Decision

Production launch is prohibited while any `BLOCKED` item above remains. The owner audit must attach evidence for each of the six external production blockers, reducing the unresolved critical blocker count to zero.

The credential-free launch-evidence verifier currently returns `no_go` with all six gates
remaining for the labeled dummy record. Its production mode requires the exact release,
image digests, migration head, infrastructure version, owners, approvals, and all required
evidence classes; even `evidence_complete` still requires accountable human approval.

The exact owner inputs and acceptable proof are defined in [`docs/PRODUCTION_HANDOFF.md`](PRODUCTION_HANDOFF.md). Do not place secret values in that document or in launch tickets.
The per-kind Hostinger procedure/artifact mapping is in
[`docs/HOSTINGER_EVIDENCE_MAP.md`](HOSTINGER_EVIDENCE_MAP.md); it does not replace any required
production artifact or approval.
