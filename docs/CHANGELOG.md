# Changelog

## 2026-08-31 — Tenant viewer-monetization foundation

- Chose one isolated Aperture cell per tenant as the initial commercial boundary, with independent
  database, Redis, storage/IAM, workers, secrets, provider connection, domains, backups, and
  observability. Documented the future control-plane lifecycle and kept platform-rental billing
  strictly separate from each tenant's viewer revenue.
- Added a disabled-by-default, owner-only Customer payments workspace with Stripe-hosted Connect
  onboarding and explicit provider-status refresh. Aperture stores only bounded non-secret account
  state; it exposes no API-key or bank-detail form and never treats an onboarding return as payment
  readiness.
- Added immutable tenant-authored viewer plans: owners create validated monthly or annual plans and
  archive-and-replace published terms instead of rewriting prices already referenced by customers.
  The storefront remains free, and subscription activation is intentionally unavailable until
  connected-account checkout, signed webhook reconciliation, entitlements, playback enforcement,
  and paid-launch evidence ship together.

## 2026-08-29 — Hostinger first-party edge, storage, and exporter artifacts

- Replaced the mutable upstream Caddy, MinIO server, Node Exporter, and Blackbox Exporter
  selections in production Compose with immutable `CADDY_IMAGE`, `STORAGE_IMAGE`,
  `NODE_EXPORTER_IMAGE`, and `BLACKBOX_IMAGE` release inputs built from reviewed first-party
  Dockerfiles.
- Extended the approved-builder workflow, strict digest validation, sanitized VPS allowlist,
  topology mappings, atomic pinning, rollback controller, examples, and version 2 launch-evidence
  record to cover API, media-worker, web, backup, Caddy, storage, node-exporter, and Blackbox as
  eight distinct artifacts. Scene keeps the API digest, producing nine explicit runtime component
  bindings.
- Preserved the disabled-payment and policy gates, literal dotenv parsing, mode-preserving atomic
  writes, and secret-redacted rollback output. No registry push or production deployment is
  claimed; local Node Exporter and Blackbox candidates each scan at 0 critical/0 high.

## 2026-08-29 — Hostinger media-worker image isolation

- Removed FFmpeg from the Python 3.12.14/Alpine 3.24 API image and introduced a dedicated,
  upgraded-Alpine media-worker Dockerfile containing FFmpeg. API, migration, Scene worker,
  maintenance, and preflight stay on the smaller API artifact.
- Threaded a distinct immutable `MEDIA_WORKER_IMAGE` through Hostinger Compose, credential
  validation, sanitized VPS rendering, approved-builder digest pinning, eight-artifact rollback,
  topology validation, evidence documentation, and focused tests without weakening policy,
  payment, or atomic-secret gates.
- Kept the nine-component launch-evidence contract: `media_worker` receives the dedicated digest,
  `scene_worker` records the shared API digest, and edge/storage/exporters record their artifacts.
  Runtime binary and vulnerability rescans remain required release evidence; no image push is
  claimed here.

## 2026-08-18 — Single credential entry point

- Made the repository-root mode-0600 `.env` the only owner-edited credential file for the
  application, Hostinger VPS, domain/TLS, immutable release, private Studio, SMTP, Stripe,
  monitoring, offsite backup, replica, restore, and rollback inputs.
- Changed Hostinger operations, release pinning/rollback, host hardening, monitoring, restore,
  and private-Studio tooling to consume the root file while allowing their focused validators to
  ignore unrelated labels safely.
- Removed redundant per-folder local dotenv files and changed clean-run CI/tests to use committed
  non-secret example fixtures.
- Added `apertures.online`, `origin.apertures.online`, `storage.apertures.online`, and
  `media.apertures.online` as the production hostname labels without replacing any credentials
  already supplied by the owner.
- Kept SSH private-key contents outside dotenv; the single file stores only its local path.
- Verified 103 unique root labels, mode `0600`, Hostinger and private-Studio structural validation,
  shell parsing, 28 Hostinger tests, and 4 private-gateway tests.

## 2026-08-17 — Expanded catalog filtering

- Added openly visible title/description search, release-period, maturity-rating, original-language, and ongoing/completed-series filters to the homepage. These combine immediately with type, country, duration, studio, and genre and reset as one state. The additional controls occupy a second responsive top panel with no dropdown menus. TypeScript, ESLint, 14/14 web tests, and the production build pass.

## 2026-08-17 — Two-level homepage filters

- Reorganized catalog filtering into a full-width top toolbar for the most-used Type, Country, and Duration controls, with Studio and Genre retained in the sticky side refinement panel. The live result count now sits in the section heading. Tablet and mobile layouts collapse both levels cleanly into one column. Live SSR verification confirms one top toolbar, all three primary filter groups, and one side panel; TypeScript, ESLint, 14/14 web tests, and the production build pass.

## 2026-08-17 — Hero key collision fix

- Fixed the React duplicate-key console error for movie UUID `90b9bebc-a4e7-49da-b30a-f41eecda12e0`. The active hero backdrop and copy panel were distinct sibling elements but shared the same raw title ID key; their keys are now role- and content-kind-namespaced, and slide-dot keys additionally include position. Catalog records were not duplicated. TypeScript, ESLint, 14/14 web tests, and the production build pass.

## 2026-08-17 — Accessible filter sizing

- Resized the open homepage filter controls around practical Fitts's Law and touch-target guidance: chips and reset actions now have a 44 px minimum height, larger and heavier labels, higher contrast, wider gaps, and a 300–350 px desktop sidebar. Responsive breakpoints preserve the full-width mobile filter layout. TypeScript, 14/14 web tests, and the production build pass.

## 2026-08-17 — Open filter option groups

- Replaced every homepage catalog-filter dropdown with openly displayed, keyboard-operable option chips. Type, country, duration, studio, and genre choices are visible in their own labeled fields; selected values have an explicit pressed state and checkmark. Long studio/genre sets use bounded visible scroll regions rather than menus. Live verification renders 134 option buttons and zero filter selects. TypeScript, ESLint, 14/14 web tests, and the production build pass.

## 2026-08-17 — Interactive homepage catalog filters

- Added a responsive homepage discovery workspace with a sticky left filter panel and automatically updating right-side title grid. Filters cover content format (movies, series, OVA), country, episode/film duration, production studio, and genre, with live result counts, combined filters, reset handling, and an actionable empty state. Extended normalized movie/series responses with source-derived format and studio metadata via reversible migration `20260817_0025`; the idempotent importer now includes an explicit TMDB-keyword OVA discovery slice rather than guessing format. The current catalog includes three verified OVA titles and 61 series-studio values. TypeScript, ESLint, 14/14 web tests, production build, focused API tests, Ruff, and zero migration drift pass.

## 2026-08-17 — Context-rich series and episode experience

- Expanded the TMDB development importer to persist episode titles, full summaries, runtimes, air dates, publication state, and high-resolution still URLs. Provider series sync is deliberately bounded to three seasons and 30 episodes per season so long-running feeds cannot generate thousand-row browser pages; the current catalog contains 524 episode stills and up to 90 contextual episodes per series. Rebuilt series details with backdrop/poster art, ongoing status, original title, genre chips, season/episode totals, About and facts sections, responsive image-backed episode rows, season selection, and six related-series cards. Migration `20260817_0024`, zero drift, focused catalog/homepage/performance tests, TypeScript, ESLint, 14/14 web tests, and the production build pass. The broader API run passed 80 tests; four object-storage integration tests were prevented by the existing local MinIO `XMinioStorageFull` state rather than an application assertion.

## 2026-08-17 — Cinematic movie detail pages

- Replaced placeholder-monogram movie details with imported poster and full-width backdrop artwork, layered readable treatment, original-title and genre context, a structured film synopsis, richer availability messaging, and a populated facts panel. Empty cast/director/theme fields are omitted instead of rendered as dashes. Removed provider branding from title and hero presentation while retaining the required catalog-source disclosure on a dedicated Data credits page linked from the global footer. The reported Ribbon Hero page returns 200 with artwork, About/Details sections, and no visible TMDB text. TypeScript, ESLint, 14/14 web tests, and the 39-route production build pass.

## 2026-08-17 — Stable hero dimensions

- Removed slide-to-slide hero reflow by reserving fixed responsive hero/copy dimensions, clamping variable titles and descriptions, containing layout/paint, and reserving the browser scrollbar gutter. Long metadata remains clipped within its designed region instead of resizing the carousel. TypeScript, 14/14 web tests, and the production build pass.

## 2026-08-17 — Hero artwork and context refinement

- Increased active hero-backdrop visibility from a translucent treatment to near-full-opacity, color-preserving artwork with a directional layered gradient behind copy. Added original-title context, year, maturity rating, runtime, country, up to three genres, source/category labeling, and a numbered slide counter. Moved large glass-backed previous/next controls to the left and right edges, centered the progress indicators, added a subtle cinematic image drift, and introduced a dedicated compact mobile composition. The active image remains the only loaded backdrop. TypeScript, 14/14 web tests, ESLint, and the production build pass.

## 2026-08-17 — Latest and ongoing hero slideshow

- Replaced the static homepage hero with a release-ordered slideshow of up to ten entries: five latest movies and five TMDB-confirmed ongoing series. It rotates every seven seconds, exposes previous/next and direct-selection controls, pauses during pointer or keyboard interaction, honors reduced-motion preferences, links each slide to the correct title, and loads only the active high-resolution backdrop. Added persisted ongoing-series metadata and reversible migration `20260817_0023`. TypeScript, ESLint, 14/14 web tests, production build, Ruff, 84/84 API tests, zero migration drift, and live ten-slide SSR verification pass.

## 2026-08-17 — Local TMDB catalog population

- Added an idempotent, development/test-only TMDB importer with stable provider IDs, source provenance, Japanese-animation discovery, normalized genres/languages/countries, series season shells, maturity metadata, and original-size poster/backdrop URLs. Imported 16 movies and 16 series, published a two-rail local homepage, added TMDB attribution, and kept metadata-only titles outside playback recommendations. Added reversible migration `20260817_0022`, optimized scheduled-state synchronization to preserve homepage query budgets, and verified zero migration drift, 84/84 API tests, Ruff, TypeScript, ESLint, production build, live API rendering, and successful remote image delivery. No credentials are committed or exposed.

## 2026-08-17 — Local completion audit

- Re-ran the local finish gate against the live hot-reload and isolated HTTPS topologies. The audit found one real adaptive-player lifecycle defect: both `pagehide` and React teardown could send an identical forced progress update, and Chromium could cancel the duplicate during navigation and report a misleading CORS console failure even though the API completed the surviving request with 200. Forced saves now de-duplicate position changes below 250 ms and use fetch keepalive for lifecycle delivery. The focused desktop journey passed after rebuilding staging, then the full deployed matrix passed 46/46 enabled-feature desktop/mobile journeys with four flag-off-only cases intentionally skipped. Ruff, 84/84 API tests, TypeScript, ESLint, 14/14 web tests, CDN 4/4, geo edge 2/2, the production web build, migration head/drift, and live dependency readiness all pass. Both local environments remain running; public production remains separately gated by six external owner/provider/legal inputs.

- Refreshed the production-shaped local acceptance evidence against the currently running isolated HTTPS stack. The immutable API and web images rebuilt, migration and seed gates passed, readiness reported PostgreSQL/Redis/object storage healthy, and Playwright passed 46/46 enabled-feature desktop/mobile Chromium journeys with four intentionally skipped all-flags-off-only cases. A fresh isolated backup restored at `b7e4c91d2a60` with 91/91 public tables, and the credential-free public-edge verifier passed six checks. Reverified that the separate Next.js/FastAPI hot-reload topology, native PostgreSQL/Redis/MinIO, and both native workers also remain alive; the service ledger now records both development and production-shaped staging instead of conflating them. Production remains NO-GO on the same six external gates.

- Added an owner-credential-ready free-tier public staging target while preserving the existing DigitalOcean Toronto production path. The target uses two Render Free web services, Supabase-compatible pooled TLS PostgreSQL, TLS Redis, private Cloudflare R2, Sentry, and SMTP. Since the free compute tier has no worker service, its staging-only supervisor co-locates FastAPI, media, and scene workers and exits the unit if any child fails. Added fully labeled ignored dummy inputs, fail-closed deploy validation, three focused validator tests, a 50 MiB demo upload ceiling, manual deploy controls, and explicit sleep/quota/worker/FFmpeg/data-residency/SLA/legal limitations. Dummy validation and manifest structure pass; deploy validation correctly rejects all dummy labels without network calls. This creates a viable no-cost public demo route but does not alter the six external production blockers.

- Closed the remaining repository-owned privacy-consent browser-evidence gap. Added a staging-only, test-environment-guarded privacy inspector and a deployed HTTPS desktop/mobile journey proving analytics defaults off, ingestion is denied before consent, the account UI records explicit consent, ingestion is accepted and persisted afterward, withdrawal deletes retained raw events, ingestion is denied again, and No Algorithm persists. The journey captures its responsive result and rejects console/request failures. It passes 2/2; the expanded standard staging matrix passes 46/46 with the four separate all-flags-off cases intentionally skipped, while TypeScript, ESLint, and 14/14 web tests remain green.

- Closed the repository-owned risky-feature browser-evidence gap. Staging feature values now remain enabled by default but can be consistently overridden across API runtime, web build, and web runtime. Added a repeatable all-flags-off staging gate with automatic restoration plus a Playwright acceptance that captures desktop/mobile screenshots, proves risky navigation is absent, proves customer and API routes fail closed with 404 rather than auth leakage, and rejects console errors, failed requests, or 5xx responses. The deployed HTTPS flag-off build passed 4/4 checks; the restored enabled build then passed its normal 44/44 Chromium matrix.

- Began the explicit distribution-territory boundary. Added short-lived HMAC-signed viewer-country assertions with ISO normalization, expiry/future-skew/tamper rejection, a required production geo secret, and labeled dummy DigitalOcean/staging inputs. Added reversible migration `b7e4c91d2a60` with indexed JSONB territory allowlists for movies, series, and editions; empty means globally licensed. Admin API schemas normalize and validate allowlists, and Studio exposes movie, series, and per-edition controls without conflating them with production country. The shared fail-closed predicate now covers primary catalog, homepage snapshots/dynamic rails/no-algorithm indexes, recommendations, Movie Prescription, knowledge graph/credit links, curated collections/journeys, community title access, club summaries/lists/scheduling, every watch-party authorization operation, SceneLens, Cinephile, After-Credits recommendations, progress, playback configuration, and media delivery. Next.js preserves signed assertions across catalog, profile-homepage, account-backed, playback, and server-rendered community API hops. Playback stores the verified country beside the atomic device lease; API media and secret CDN-origin misses recheck title and edition rights against that lease. CDN grants and cache namespaces are country-bound, so changing a URL territory invalidates its HMAC and a changed active lease invalidates the origin request. Added a deployable trusted web/API ingress Worker that overwrites spoofed assertions with an HMAC of Cloudflare's viewer country and fails closed when region or configuration is missing. Homepage configuration loading was collapsed from three reads to one joined read to preserve its six-statement budget after the enforcement audit. Migration roundtrip and zero-drift check, 84/84 API tests, Ruff, four CDN edge tests, two geo-ingress tests, 14 web tests, TypeScript, ESLint, and dummy Toronto spec rendering pass. The production Next.js build exposed and prompted removal of a client/server module-boundary leak in the series browser; the rebuilt isolated HTTPS staging stack then passed 44/44 desktop/mobile Chromium journeys, and its backup restored at `b7e4c91d2a60` with 91/91 public tables. Real geo-edge deployment and public multi-country acceptance remain external; end-to-end production completion is not claimed.

## 2026-08-16 — DigitalOcean Toronto and Stripe production readiness

- Converted `simultaneous_streams` from display-only plan metadata into an enforced playback boundary. An atomic Redis sorted-set lease admits distinct active device sessions only up to the current entitlement, refreshes an existing session without consuming a slot, expires abandoned sessions, rejects inactive media leases, fails closed on coordination outages, and validates that production lease lifetime covers the CDN token. Movie and episode watch pages now show an actionable recovery state for limit and coordination failures. The live generated-player journey proves the first stream remains active while a second authenticated device is denied with that state on desktop and mobile. API tests pass 77/77; web checks pass 14/14 with TypeScript, ESLint, and production build green.
- Reconciled the integrated staging stack to migration `91f3a6c2d8b4` and repeated an isolated backup/restore with 91/91 tables. Fixed three acceptance-discovered boundary defects: customer feature routes were accidentally subjected to Studio-cookie enforcement, multipart part URLs used the private container endpoint instead of the configured browser endpoint, and locale-dependent scan timestamps caused hydration mismatches. Browser acceptance now explicitly grants analytics consent before asserting QoE collection and waits for authoritative preference writes. The complete current-schema Chromium desktop/mobile matrix passes 44/44; API tests pass 75/75 and web component/unit checks pass 13/13.
- Added quarantined malware verdicts for uploaded masters, an EICAR test scanner, a bounded ClamAV INSTREAM adapter, retry-safe scanner outage handling, production-only private-clamd configuration, and a secret-safe preflight PING. Studio now shows pending/error/clean/infected scan states, never offers processing without a clean verdict, preserves post-transfer quarantine, and supports scan-only retry. Real MinIO tests prove clean, detected, unavailable, and recovered outcomes; protocol/config and UI tests prove framing, verdict parsing, production rejection of the test scanner, and operator controls. Reversible migration `91f3a6c2d8b4`, zero drift, 75/75 API tests, and 8/8 web tests pass.
- Added default-off per-profile optional analytics consent with a dedicated privacy endpoint, consent timestamp, ingestion denial, and transactional raw-event deletion on withdrawal. Account controls distinguish optional analytics from required resume progress. No Algorithm now makes Discover ignore profile watch history/preferences and disclose editorial/anonymous-aggregate ranking. Reversible migration `4d91c8a7f2e0`, zero drift, 70 API tests, five web tests, and production build pass.
- Added an eight-document legal-policy publishing package, approved-only routes/footer, true 404 boundaries for pending/unknown policies, and a production build/deploy gate rejecting missing approval metadata, dummy/TODO markers, empty sections, or insubstantial text. Five web tests, build, live pending-policy HTTP acceptance, dummy render, and deploy-input rejection pass; final policy text and approval remain external.
- Added a versioned, secret-free production launch evidence record and fail-closed verifier for the six external blockers. It requires exact release/four-image/migration/infrastructure identity, owners, approvals, timezone-aware observations, and named evidence classes; rejects dummy markers, likely secrets, missing evidence and self-approval; and always preserves final human authority. Seven focused verifier tests and the full 70-test API suite pass; the dummy record correctly remains NO-GO.
- Added fail-closed runtime feature flags for SceneLens, Ask This Movie, Community, watch parties, and experimental recommendations. Parent customer routers are omitted at startup, independent child actions return a non-enumerating 404, and DigitalOcean/staging inputs are explicit.
- Completed navigation-aware flag handling: disabled links, movie community content, player Lens/Ask controls, party creation, and direct pages are removed or return true 404. Added synchronized public/server DigitalOcean owner labels with strict boolean and parent/child validation. Four web tests, both enabled/disabled builds, and isolated HTTP acceptance pass; interactive browser flag-off review remains explicitly unproved because its supported runtime was unavailable.
- Re-audited Command A against current evidence and promoted resumable multipart upload plus production CDN delivery from soft scaling notes to explicit internal NO-GO gaps in `docs/INTERNAL_GAP_AUDIT.md`; removed stale status claiming the already-completed staging phases were still next.
- Implemented durable resumable multipart intake: PostgreSQL-owned sessions, 16 MiB private signed parts, storage-authoritative resume state and ETags, contiguous completion, safe abort, full streamed integrity validation, and Studio pause/reselection resume. Real MinIO API interruption and Chromium interruption/resume pass; migration `d2b94a1786ef` round-trips cleanly and 61 API tests pass.
- Implemented protected production CDN delivery through a deployable token-validating edge adjunct while retaining DigitalOcean for the application and private Spaces origin. Source/session/expiry HMAC grants are verified before cache lookup; misses use a separate origin secret and revalidate active session, rights, source and object path; ranges bypass cache; CSP/CORS and credential behavior are integrated. All 61 API tests and four edge tests pass, including tampering, expiry, cache hits, ranges, and fail-closed lifetime configuration. Provider deployment remains an external blocker.
- Added a credential-free DigitalOcean App Platform template targeting Toronto, attached managed PostgreSQL/Valkey bindables, private versioned Spaces configuration, pre-deploy migration, redundant web/API services, and separately supervised media/scene workers.
- Added Stripe subscription Checkout, customer/plan metadata, signed webhook verification, idempotent event persistence, provider-authoritative subscription state, and entitlement reconciliation.
- Added fail-closed production live-key validation while permitting mocked/test credentials outside production; automated fake-credential tests never contact Stripe.
- Adapted storage preflight for DigitalOcean Spaces' partial S3 API: a private ACL with no policy passes, present policies are parsed conservatively, and any anonymous GetObject/ListBucket allow fails.
- Added a fully labeled, git-ignored mode-0600 credential input, harmless dummy values, and a secret-silent renderer. Deploy mode rejects every dummy marker, Stripe test key, invalid webhook-secret prefix, and short security secret before producing deployment files.
- Connected customer plan controls to Stripe Checkout, prevented duplicate active subscriptions, added provider Billing Portal handoff for payment methods/cancellations/plan management, and persisted idempotent invoice-paid/payment-failed references with immediate past-due state.
- Corrected the DigitalOcean web build contract by supplying both required `NEXT_PUBLIC_*` origins, and changed the renderer to remove its template-only extension before emitting the provider spec. Database, Stripe, Spaces, SMTP, monitoring, and session credentials are now scoped only to the API, migration, and worker components—not the web container.
- Added deterministic Stripe Checkout idempotency and fail-closed ownership/provider/customer consistency checks during webhook reconciliation. Billing Portal lookup now requires the configured provider, preventing a reference from another provider being sent to Stripe.
- Corrected Spaces delivery configuration so browser PUT signatures target the private bucket origin rather than a CDN hostname, and removed a blanket deny policy that would also have blocked authenticated API/worker reads.
- Built and inspected the current production API/web images with dummy Toronto inputs: both are non-root, the API contains Stripe and migrations, and the compiled web bundle contains the configured public API origin.
- Replaced deprecated per-service App Platform routes with ordered current ingress rules (`/api` before `/`) and added provider-native deployment/domain failure alerts to the rendered target.
- Added a tested five-minute UTC scheduled job that materializes due catalog publication/archive transitions and purges expired raw analytics in bounded batches without depending on incoming customer traffic.
- Extended full production preflight with a secret-safe read-only Stripe account authentication check; invalid credentials or connectivity now fail launch validation without creating or changing billing objects.
- Made webhook processing resilient to out-of-order Stripe deliveries by retrieving the provider's current subscription/invoice object before reconciliation. Invoice events persist payment outcomes, while provider-authoritative subscription events own entitlement and past-due state.
- Added the full read-only production preflight as a DigitalOcean `POST_DEPLOY` release job, complementing the blocking `PRE_DEPLOY` migration and scheduled maintenance jobs.
- Added a daily non-root PostgreSQL 17 backup job with a backup-only Spaces identity, custom-format dump, SHA-256/migration/table-count manifest, private uploads, and credential-redacted failure logging. Scheduling is ready, while a real isolated restore and measured RPO/RTO remain launch blockers.
- Added a production restore verifier that requires an explicit confirmation and `aperture_restore_` empty target, validates manifest/object binding, size and SHA-256 before restore, then proves migration head and table count. A local production-format rehearsal restored 90 tables at `7f3d28a8d301` in 1.293 seconds; provider evidence remains outstanding.
- Added a credential-redacted DigitalOcean rollback controller with network-free dummy validation, read-only inspection of an explicitly selected successful deployment, an exact execution confirmation, and tested payload/failure behavior. Live traffic rollback and post-rollback acceptance remain provider gates.
- Added a credential-free public-edge smoke verifier for HTTPS, security headers, request-ID propagation, dependency readiness, fail-closed protected APIs, and hidden production documentation. It passed six non-mutating checks against the isolated staging TLS edge; real public DNS/TLS evidence remains outstanding.
- Added PostgreSQL-authoritative media-worker leases with row-locked claims, UUID ownership, heartbeats, stale-owner write rejection, bounded expired-job recovery, and a configurable terminal attempt limit. The Toronto target now runs two media workers; the reversible lease migration and 59-test regression pass.
- Extended the lease model to Scene enrichment, including transactional ownership revalidation before transcript/search replacement, stale-owner rejection, bounded requeue, and attempt-exhaustion failure. The Toronto target now runs two scene workers; migration `8a2d7e914bc0`, rollback/re-upgrade/drift, and 60 API tests pass.

### Phase 31 — Production Launch Gate (No-Go)

- Closed Phase 30 at 42/42 deployed HTTPS Chromium checks with real media, SceneLens, subscription entitlements, and staging SMTP password reset.
- Eliminated concurrent progress-write deadlocks with a profile/source transaction lock and a four-way API concurrency regression.
- Added operational Studio TOTP enrollment, one-time recovery codes, desktop/mobile sign-out, and recovery-code reauthentication acceptance.
- Added repeatable staging database/config backup, verified isolated restore at the exact migration head with all 90 public tables, and private MinIO versioning.
- Expanded Playwright to mobile/tablet/laptop/large-desktop Chromium, Firefox, and WebKit; fixed an 834 px header overlap and Safari-compatible keyboard focus handling.
- Proved the generated adaptive player, subtitles, resume, SceneLens, and QoE path in Firefox and WebKit.
- Replaced Studio Users, Subscriptions, and Storage placeholders with server-authorized operational dashboards. Customer support actions require reasons, revoke sessions safely, exclude authentication/provider secrets from export, and write administrator audit records; billing stays provider-authoritative and storage exposes versioning/health without credentials or keys.
- Expanded customer export into a versioned portable record covering preferences, playback history, SceneLens memory, analytics, curation, community, sessions, billing summaries, and entitlements. Added exact-email/exact-phrase/reason/authorization confirmed deletion with database cascades and a non-identifying audit tombstone.
- Fixed mobile support-table action reachability, forced the session-derived locale bridge to remain private and uncached, and removed a cross-test catalog race by making moderation acceptance use the immutable seeded title.
- Added API and deployed desktop/mobile acceptance for support authorization, customer controls/export, subscription visibility, and storage durability signals; the current gates pass 33/33 API and 42/42 HTTPS browser checks.
- Added `docs/LAUNCH_CHECKLIST.md`; production remains an explicit NO-GO with six external production blockers and zero claim of deployment.
- Added a provider-neutral production owner handoff contract covering exact configuration inputs, secret delivery, infrastructure acceptance, backup/rollback evidence, alert routing, rights/policy packages, and the final production acceptance record.
- Added a provider-neutral production preflight inside the API image. It validates production settings, exact Alembic head, PostgreSQL, Redis, private/versioned object storage, and SMTP authentication without mutation, sending email, or exposing exception/credential details.

## 2026-08-15

### Phase 27 — Security Hardening (Pass)

- Disabled FastAPI documentation/OpenAPI routes outside development, added production HSTS, CSP, frame, MIME, referrer, and permissions protections, and applied equivalent restrictive browser headers through Next.js.
- Restricted CORS request headers and strengthened unsafe-request origin enforcement so production rejects both missing and forged origins while trusted Next.js server actions identify the configured web origin explicitly.
- Preserved signed direct uploads under CSP by allowlisting only the configured public object-storage origin; upload completion still validates size, checksum metadata, streamed SHA-256, and container signature.
- Added production configuration rejection for placeholder database/object-storage credentials and insecure public origins, retaining existing strong session, SMTP, and real billing-provider requirements.
- Audited administrator routing/provisioning, session hashing/revocation/cookies, private media path/range delivery, development-only E2E helpers/reset tokens, repository secret signatures, dependencies, and public debug surfaces.
- Closed Phase 27 with 40 browser tests, 28 API tests, Ruff, ESLint, TypeScript, Vitest, production build, and a zero-vulnerability npm audit passing.

### Phase 28 — Performance Hardening (Pass)

- Established live development baselines for route TTFB/download size, browser DOMContentLoaded/resource/script transfer, API warm/cold latency, dependency readiness, shipped chunk size, and SQL statement counts.
- Removed two redundant full catalog requests from the normal customer homepage path. Movie and series hierarchy payloads are now fetched only when no published/profile homepage hero or rails exist.
- Added bounded SQL-statement regression coverage for movie, series, and homepage reads, proving eager-loading query counts stay constant as result counts grow.
- Added desktop/mobile browser budgets for homepage DOMContentLoaded, resource count, and transferred JavaScript; the current live baseline is approximately 752 ms, 18 resources, and 787 KB in the development server.
- Added durable bounded playback-startup, buffer, fatal-error, and quality-change events. Real generated HLS acceptance proves first-frame and manual/Auto rendition measurements reach analytics without blocking playback.
- Added Studio QoE reporting for average startup, sample count, buffering seconds, fatal-error rate, and quality changes.
- Removed Studio Analytics title-label N+1 reads by bulk loading movie and episode labels; the complete summary remains bounded to seven statements including administrator authentication.
- Benchmarked the isolated local Redis queue at roughly 257k enqueues and 293k claims per second; generated 12-second 720p media completes the real upload/transcode/validate/assignment path in approximately 9–10 seconds under the browser gate.
- Closed Phase 28 with 42 desktop/mobile browser journeys, 30 API tests, measured browser/query budgets, reversible QoE migration and zero drift, Ruff, ESLint, TypeScript, Vitest, production build, zero-vulnerability audit, and live dependency readiness passing.

### Phase 29 — Production Observability (Pass)

- Added correlation-safe `X-Request-ID` handling, structured JSON request/worker lifecycle logs, bounded route-template API metrics, and exception capture through the official Sentry SDK with default PII collection disabled.
- Production now requires an environment-specific error-tracking DSN and strong metrics bearer token; `/metrics` is omitted from API documentation and refuses unauthenticated reads.
- Added Prometheus-compatible API request/duration/in-flight, queue backlog, queued age, processing state/failure, transcode duration, registered storage, storage availability, scene-job, and recent playback QoE signals.
- Hardened readiness to check database, Redis, and object storage independently with three-second timeouts and a fail-closed 503 response naming only dependency state.
- Added a protected Studio Operations destination with live queue, storage, transcode, worker-state, and active-threshold reporting.
- Added deployable alert rules and incident runbooks for failed media processing, database/storage outages, queue backlog, CDN/origin faults, administrator lockout, and bad deployments.
- Added live recent playback start/buffer/error metrics for CDN/origin alerting, repeated administrator-denial detection, API availability/error-rate rules, and external readiness-probe failure detection.
- Closed Phase 29 with 42 desktop/mobile browser journeys, 32 API tests, parsed nine-rule alert configuration, verified JSON correlation output, live authenticated metric/readiness scrapes, Ruff, ESLint, TypeScript, Vitest, production build, and zero-vulnerability audit passing.

### Phase 26 — Accessibility and Internationalization Pass (Pass)

- Added a global keyboard-visible skip link, consistent high-contrast focus treatment, reduced-motion preservation, and logical-direction RTL header/action behavior without horizontal overflow.
- Added automated WCAG 2 A/AA and 2.1 A/AA checks across representative public, authenticated account, and authenticated Studio surfaces on desktop and mobile; corrected primary-action and Studio navigation/status contrast failures found by the audit.
- Added modal focus entry, tab containment, Escape dismissal, and opener/fallback focus restoration for SceneLens and the After-Credits Room.
- Added validated per-profile IANA timezone, interface language, preferred audio, primary/secondary subtitle, subtitle-default, caption size, caption background, and caption position preferences through reversible migrations.
- Added a same-origin semantic locale bridge that applies the active profile language and RTL direction to the document without producing unauthorized console noise for anonymous or administrator-only sessions.
- Added locale-aware currency and timezone-aware session formatting plus a responsive account preference editor.
- Carried audio/caption preferences into the authorized playback contract. The player matches ISO 639 two/three-letter aliases, preserves the native primary subtitle track, optionally displays a distinct second licensed track, and applies small/medium/large, transparent/shadow/solid, and top/bottom caption presentation.
- Extended real media acceptance to embed, process, expose, select, and render English and French WebVTT tracks while proving the primary and second selectors remain independent and responsive.
- Closed Phase 26 with 40 browser tests, 25 API tests, production build, lint, types, unit tests, zero-vulnerability audit, two-migration rollback/re-upgrade/drift checks, live readiness, automated WCAG checks, and desktop/mobile visual review passing.

### Phase 25 — Movie Clubs / Watch Parties (Pass)

- Added the reversible persistence foundation for private clubs, owner/moderator/member roles, membership lifecycle, scheduled assigned films, polls/options/profile-unique votes, spoiler-aware private discussion, shared club lists, and per-member watch history.
- Added private watch-party state with one assigned Ready playback source, host identity, hashed access token, participant join/leave and entitlement-verification timestamps, monotonic revisions, host play/pause/seek/end events, bounded positions, and party chat/reactions.
- Added authenticated club creation/join, member-role management, scheduling, voting, discussion/removal, list attachment, and responsive club-hub workflows.
- Added private party creation/join, host-only optimistic playback control, two-second polling and drift correction, chat/reactions, participant presence, end/leave lifecycle, and completed member history.
- Reused normal source, title-rights, region, session, and active-profile authorization on every party read and mutation so the room credential never grants media entitlement.
- Added conflict handling for duplicate parties and stale host revisions, ended-party admission denial, hashed invite credentials, and Redis mutation limits.
- Closed Phase 25 with 36 browser tests, 25 API tests, production build, lint, types, unit tests, zero-vulnerability audit, migration rollback/re-upgrade/drift checks, live readiness, and desktop/mobile visual review passing.

### Phase 24 — Reviews and Community (Pass)

- Added the first fail-closed moderated-community persistence foundation: profile/movie ratings, spoiler-aware reviews, profile follows, block/mute safety relations, abuse reports, immutable administrator moderation actions, and typed activity records.
- Extended the shared profile-owned list aggregate with private/unlisted/public visibility and moderation state rather than creating a competing community-list table.
- Added database invariants for rating range, one review per profile/movie, bounded nonempty review bodies, no self-follow/block/mute, one report target, one moderation-action target, and activity-kind-specific target shape.
- Added active-profile rating and spoiler-aware review workflows; review creation and every edit enter pending moderation, and only approved reviews can reach another viewer.
- Added Redis profile-weighted limits for ratings, review edits, lists, reports, follows, and block/mute writes plus duplicate-report conflict handling.
- Added approved public-list discovery over the existing ordered user-list aggregate, owner visibility controls, safety-filtered direct destinations, and fresh moderation after list edits.
- Added follow/unfollow and typed activity feeds that expose only still-approved review/list targets from followed profiles and suppress blocked or muted actors and targets.
- Added customer report, follow, mute, and block actions directly beside approved reviews. Blocking removes either-direction follows and prevents either profile from following again until unblocked.
- Added an authenticated Community destination for approved lists and following activity plus a responsive movie rating/review form with collapsed spoiler content.
- Added a protected Studio moderation queue for reviews, public lists, and abuse reports; every decision requires a reason, writes an immutable moderation action and administrator audit record, and publishes activity only on approval.
- Preserved account deletion by allowing retained moderation actions to become target tombstones while retaining their administrator, decision, reason, and time.
- Closed Phase 24 with 34 browser tests, 24 API tests, production build, lint, types, unit tests, zero-vulnerability audit, migration rollback/re-upgrade/drift checks, live readiness, and desktop/mobile customer/moderator visual review passing.

### Phase 23 — No-Algorithm Mode (Pass)

- Added reversible migration `20260815_0021` for an explicit curated/no-algorithm homepage strategy stored independently on every profile.
- Added authenticated active-profile homepage rendering and one atomic mode-write endpoint; switching returns the newly selected strategy immediately and another profile retains its own choice.
- Added the named deterministic `deterministic_catalog_indexes_v1` projection over currently published, in-rights movies and series with stable recently-added, A–Z, release-year, director, country, genre, and published-collection rails.
- Kept No-Algorithm Mode independent of viewing behavior, recommendations, popularity, inferred taste, and random ordering; the response and customer UI disclose the active strategy plainly.
- Added a responsive homepage strategy panel with immediate Curated/No Algorithm switching and persistence across reloads.
- Proved invalid modes fail validation, repeated reads are stable, profile choices remain isolated, and desktop/mobile switching renders without console or network failures.
- Closed Phase 23 with 32 browser tests, 22 API tests, production build, lint, types, unit tests, zero-vulnerability audit, migration rollback/re-upgrade/drift checks, live readiness, and responsive visual review passing.

### Phase 22 — Cinephile Toolkit (Pass)

- Audited the toolkit against shared scene, catalog, artwork, credit, edition, playback, and viewing-activity domains to avoid one-off feature storage.
- Added reversible migration `20260815_0016` for scene-attached, timestamped, rights-documented, explicitly permitted still artwork with invariant-preserving cascade lifecycle.
- Added an authenticated source-level Cinephile contract for protected stills, music, filmmaking notes, normalized credits, editions, and private rewatch facts.
- Added authorized private still streaming without customer-visible storage keys or legal-basis text.
- Added responsive SceneLens gallery, music timeline, filmmaking explorer, credits explorer, edition empty state, and rewatch summary.
- Proved a generated permitted still remains hidden before its exact reveal boundary, plus timestamp-safe score/camera metadata and desktop/mobile rendering.
- Added reversible migration `20260815_0017` for independently processed edition sources, rights windows, intended-presentation metadata, and sourced verified edition differences.
- Added deterministic default-edition playback, edition/title assignment validation, original-language audio preference, and preserved contain-fit video presentation.
- Expanded Edition Vault with availability, real track inventories, aspect/frame/capture/audio/restoration/source details, and completion-locked comparison records.
- Proved two separately assigned edition sources can coexist, comparisons remain absent before completion and unlock afterward, and the intended presentation renders responsively in SceneLens.
- Added a customer-facing film knowledge graph built from visible normalized taxonomies, locale, franchise, people/roles, companies, characters, and shared-credit title connections, with no inferred influences.
- Added responsive linked node cards and an accessible relationship list to movie pages.
- Added navigable person/company Credits Explorer pages with publication/rights-filtered movie, series, and episode credits, role labels, and character context.
- Proved the graph and actor filmography at the API boundary and exercised generated director → person destination → exact film navigation on desktop/mobile.
- Added reversible migration `20260815_0018` for ordered editorial collections, profile-owned private lists, chaptered film journeys, and profile-specific journey completion.
- Added administrator curation APIs that create, publish, and atomically reorder collection and journey content without source changes.
- Added rights-filtered collection and journey discovery plus customer Collection and Film Journey routes; unavailable titles never leak through item payloads or completion totals.
- Added private user-list ownership enforcement and journey progress isolation, with focused acceptance covering rights expiry, cross-profile denial, and completion.
- Added a completion-gated After-Credits Room derived from the durable per-profile viewing ledger and published, provenance-backed scene intelligence.
- Restricted deeper-content records to explicit ending-analysis, easter-egg, production-story, behind-the-scenes, deleted-scene, commentary, and licensed-critical-essay categories; arbitrary production notes are not promoted into the room.
- Added verified filmmaker destinations and rights-filtered franchise/next-episode discovery without fabricating absent recommendations.
- Added a responsive end-of-playback room and browser acceptance proving it opens only after progress persistence; ratings and community discussion remain explicitly unavailable pending the moderated community phase.
- Added reversible migration `20260815_0019` for directed sequel, prequel, remake, adaptation, source-material, influence, and companion-film facts with required private provenance notes and explicit manual verification.
- Integrated verified title facts into the navigable film knowledge graph while filtering draft and rights-expired destinations and withholding private source notes.
- Added a responsive Studio knowledge ledger for creating and deleting directed title facts without source changes.
- Hardened scene enrichment against duplicate delivery with row-level job claiming and idempotent search-document upserts after the full regression suite exposed a live-worker/test race.
- Added reversible migration `20260815_0020` and an account-level profile control for optional rewatch intelligence.
- Expanded the Cinephile toolkit to surface prior completion time, saved scenes, and private notes only after a genuine rewatch starts and only while that profile has opted in.
- Proved the rewatch payload remains profile-private and is immediately emptied when disabled; ratings, rating changes, and favorite history remain absent rather than fabricated until their owning persistence phase.
- Added a responsive Studio curation editor for collection lifecycle and ordered items plus multi-chapter Film Journey composition, essays, ordered titles, and publication.
- Added profile-private Film Journey progress controls with completion/reversal and an honest private progress summary.
- Connected the shared private-list domain to a movie-detail My List action and a dedicated active-profile library, including intentional sign-in routing for anonymous viewers.
- Added a scene-aware Studio permitted-still editor that restricts selection to published scenes and worker-derived thumbnail assets while requiring an exact reveal time, accessibility text, documented rights basis, and explicit gallery permission.
- Closed Phase 22 with 30 browser tests across desktop/mobile, 21 API tests, production build, lint, types, unit tests, zero-vulnerability audit, migration rollback/re-upgrade/drift checks, live readiness, and responsive visual review passing.

### Phase 21 — Dynamic Relationship Graph (Pass)

- Added an authenticated playable-source graph endpoint derived exclusively from the published protected spoiler context and inclusive timestamp cutoff.
- Canonicalized recurring entities, required revealed endpoints, excluded orphan/future edges, sorted output deterministically, and marked matching current-scene character nodes.
- Added a responsive labeled SVG graph with bounded zoom, scroll/pan, emphasized current characters, accessible SVG description, and a semantic relationship/reveal-time list.
- Extended the live generated-media fixture with provenance-backed entities and a relationship, then exercised graph zoom and the alternate representation on desktop and mobile.
- Proved edge absence immediately before reveal, availability exactly at reveal, and future-edge suppression in a dense four-character ensemble.
- Closed Phase 21 with 30 browser tests, 19 API tests, production build, lint, types, unit tests, zero-vulnerability audit, zero schema drift, live readiness, and desktop/mobile visual review passing.

### Phase 20 — Who Was That and What Did I Miss (Pass)

- Added explicit SceneLens actions for verified current-scene character/actor identification and a last-30-seconds watched-interval recap.
- Returned prior approved appearances, spoiler-safe appearance summaries, and only already-revealed known relationships; future relationship endpoints and facts remain filtered.
- Restricted recaps to completed approved scene summaries inside a validated past interval, rejecting future, reversed, and over-15-minute ranges.
- Added dense four-character ensemble tests with planted future facts, end-to-end supported/unavailable boundary coverage, and desktop/mobile no-fabrication browser acceptance.
- Removed a repeated-run search-test ordering assumption by asserting the newly indexed scene is present among global matches.
- Closed Phase 20 with 30 browser tests, 18 API tests, production build, lint, types, unit tests, zero-vulnerability audit, migration rollback/re-upgrade/drift checks, live readiness, and desktop/mobile visual review passing.

### Phase 19 — Ask This Movie (Pass)

- Added the in-SceneLens Ask This Movie workflow backed by a transparent `structured_templates_v1` evidence router rather than an unconfigured or falsely claimed AI model.
- Bound every answer to active profile, playable source, published version, timestamp, spoiler mode, and the Phase 17 allowed structured fact set.
- Added grounded answer templates for characters/actors, completed-scene recaps, relationships, music, production notes, and named entities with explicit unavailable/uncertainty behavior.
- Added per-profile Redis throttling and typed strategy/confidence/evidence/safety response state.
- Added reversible migration `20260815_0015` for privacy-minimized internal provenance logs using question hashes and exact fact IDs without raw question retention.
- Proved supported character/actor answers, pre-ending summary refusal, exact ending availability, unsupported refusal, evidence timestamps, and browser-visible no-fabrication behavior.
- Closed Phase 19 with 30 browser tests, 16 API tests, production build, lint, types, unit tests, zero-vulnerability audit, migration rollback/re-upgrade/drift checks, readiness, and desktop/mobile visual review passing.

### Phase 18 — SceneLens (Pass)

- Added a responsive player-integrated SceneLens side panel/bottom sheet with explicit control, pause affordance, `L` shortcut, and non-obscuring layout.
- Routed current-scene, summary, character/actor, prior-appearance, relationship, music, and production/detail modules exclusively through the Phase 17 spoiler-safe context API.
- Enriched character facts from normalized title credits without using potentially future-spoiling global biographies; absent evidence remains labeled unavailable.
- Added reversible migration `20260815_0014` for profile-private timestamped scene bookmarks and notes with scene/source validation and owner-only deletion.
- Added in-player bookmark/note workflows and desktop/mobile acceptance proving the scene summary stays hidden before its reveal boundary.
- Tuned the CPU-intensive browser suite to two parallel workers and 15-second assertion tolerance after four-worker FFmpeg saturation produced false timeout failures; the resulting full suite is deterministic and remains parallel.
- Closed Phase 18 with 30 browser tests, 16 API tests, production build, lint, types, unit tests, zero-vulnerability audit, migration rollback/re-upgrade/drift checks, readiness, and desktop/mobile visual review passing.

### Phase 17 — Spoiler Safety Engine (Pass)

- Added an authenticated active-profile scene-context API backed only by the currently published evidence version for a playable movie/episode source.
- Defined inclusive reveal equality and fail-closed filtering for scenes, characters, entities, relationships, music cues, production notes, spoiler boundaries, and transcript cues.
- Made relationship reveal the maximum of the relationship and both participating entities, and delayed scene summaries/transcript text until their end timestamps.
- Gated full-spoiler mode on persisted profile/title completion while preserving the unlock through rewatch cycles.
- Added explicit withheld counts and safe states for absent published evidence and malformed/non-finite/cross-version records.
- Proved before/exact/after timestamp behavior, later relationship and ending suppression, full-mode locking/unlocking, rewatch behavior, malformed metadata omission, and invalid timestamp rejection.
- Closed Phase 17 with 30 browser regressions, 16 API tests, production build, lint, types, unit tests, zero-vulnerability dependency audit, zero schema drift, live readiness, and prior visual acceptance passing.

### Phase 16 — Scene Segmentation and Metadata Enrichment (Pass)

- Added reversible migration `20260815_0013` for aligned transcript cues and generated PostgreSQL full-text scene documents with a GIN search index.
- Added a Redis-backed enrichment worker that consumes only extracted tracks backed by administrator-declared provenance/license basis, with bounded WebVTT parsing and safe failure states.
- Added conservative cue-gap segmentation, existing-scene alignment, extractive sourced summaries, durable cue storage, and ranked scene search without embeddings or guessed characters/filmmaking metadata.
- Added Studio evidence discovery, license guidance, enrichment state/error visibility, retry-by-new-job behavior, and indexed scene search.
- Extended the generated-video browser journey with original embedded captions through extraction, provenance declaration, enrichment, indexing, search, validation, publication, desktop/mobile rendering, and visual review.
- Fixed UTC day aggregation across local-midnight boundaries and made durable aggregate acceptance repeat-safe.
- Closed Phase 16 with 30 browser tests, 16 API/unit tests, production build, lint, types, unit tests, zero-vulnerability dependency audit, migration rollback/re-upgrade/drift checks, live readiness, and visual review passing.

### Phase 15 — Scene Intelligence Data Foundation (Pass)

- Added reversible migration `20260815_0012` for versioned scene evidence, provenance, scenes, chapters, characters, entities, relationships, music cues, production notes, spoiler boundaries, and enrichment-job state.
- Added protected and audited Studio APIs with typed bounds, immutable validated/published versions, source ownership, manual correction, structural validation, queue deduplication, and atomic publication.
- Added a responsive Scene Data Studio destination for evidence-source/license capture, scene entry/editing, validation feedback, enrichment queueing, and publication, with no premature chatbot/customer surface.
- Extended API coverage across every structured record family and real browser acceptance through generated playback assignment, evidence-version creation, validation, publication, and visual inspection.
- Closed Phase 15 with 30 browser tests, 12 API tests, production build, lint, types, unit tests, zero-vulnerability dependency audit, migration rollback/re-upgrade/drift checks, live readiness, and visual review passing.

### Phase 14 — Cinema Passport (Pass)

- Added a durable profile viewing-activity ledger with bounded observed seconds, cycle numbers, completion timestamps, and explicit first-watch/rewatch classification.
- Backfilled existing progress through reversible migration `20260815_0011` and added indexed profile/year-ready history dimensions.
- Added private lifetime and yearly Passport APIs deriving film/episode counts, observed hours, completed views, first watches, rewatches, genre/country/decade distributions, credited creators, longest/shortest titles, milestones, and history solely from persisted activity.
- Added the responsive Cinema Passport experience with yearly navigation, coverage-aware empty states, privacy disclosure, statistics, distributions, creators, and activity ledger.
- Extended real playback acceptance so a browser-created and processed movie completes, appears in Passport, and remains reflected in Studio analytics.
- Added API proof of a first completion followed by a distinct rewatch plus exact creator and year aggregation.
- Fixed and regression-tested a mobile Studio Homepage inline pin-action hit target uncovered by the full suite.
- Closed Phase 14 with 30 browser tests, 12 API tests, production build, lint, types, unit tests, dependency audit, migration roundtrip/drift check, live readiness, and responsive visual review passing.

### Phase 13 — Movie Prescription and Taste DNA (Pass)

- Added active-profile Taste DNA derived solely from persisted watch progress, with weighted catalog affinities, completion/runtime behavior, evidence counts, confidence, and understandable insights.
- Added bounded, validated Movie Prescription inputs covering time, mood, pacing, intensity, genre inclusion/exclusion, unwanted characteristics, language, release era, and viewing-history intent.
- Added hard availability/constraint filtering and deterministic best-fit scoring with real taxonomy/history evidence, explicit unavailable metadata states, and no fabricated explanations.
- Added one-movie output with match score, reason, match dimensions, View & Play, and exclusion-backed Another Recommendation behavior.
- Added the responsive Prescription customer experience and desktop/mobile visual acceptance.
- Proved with two persisted profile histories that Taste DNA and prescribed movies differ meaningfully by active profile.
- Closed Phase 13 with 30 browser tests, 12 API tests, production build, lint, types, unit tests, dependency audit, schema drift check, live readiness, and responsive visual review passing.

### Phase 12 — Recommendations (Pass)

- Added an authenticated, deterministic `rules_v1` recommendation service for published movies and series; no machine-learning model is claimed or implied.
- Combined published homepage editorial signals, watched-title genre/theme/tag similarity, validated profile genre preferences, recent aggregate popularity, and cold-start fallback with stable ordering.
- Excluded profile-watched movies and episode-owning series and returned both exclusion counts and explicit reason codes with every candidate.
- Added the responsive Discover experience with human-readable explanations and an explicit disclosure of how ranking works.
- Added API coverage for authentication, cold start, preference normalization/influence, similarity, popularity, and watched exclusion.
- Closed Phase 12 with 30 browser tests, 12 API tests, production build, lint, types, unit tests, dependency audit, schema drift check, readiness, and desktop/mobile visual review passing.

### Phase 11 — Analytics Foundation (Pass)

- Added typed raw analytics events and separate daily aggregates for customer, playback, search, community, and advanced-feature signal families.
- Added authenticated profile/session ownership, client idempotency, progress-bucket coalescing, weighted Redis throttling, batch and payload ceilings, UTC event windows, and an allowlist that rejects unsupported event properties.
- Added configurable raw retention with bounded cleanup, bot/internal distinction, and aggregate exclusion behavior.
- Added platform, unique-viewer, watch-time, completion, search, and per-title aggregation plus an administrator-only recent raw stream.
- Instrumented real adaptive playback for play-start/progress/pause/seek/completion and signed-in search for query/result counts; anonymous search no longer emits authenticated requests or console noise.
- Added a responsive Studio Analytics product surface with KPI, daily, title, retention, and restricted-raw-event views.
- Extended generated-video browser acceptance to prove exact events reach PostgreSQL and become visible in Studio Analytics on desktop and mobile.
- Closed Phase 11 with 28 browser tests, 11 API tests, production build, lint, types, unit tests, dependency audit, migration roundtrip/drift check, live readiness, and responsive visual review passing.

### Phase 10 — Account and Subscription Architecture (Pass)

- Added Plan, Subscription, PaymentReference, and Entitlement models with lifecycle enums, provider-safe references, time-window constraints, and a reversible migration.
- Seeded two active plan definitions while keeping customer subscription state empty until a real provider confirms it.
- Added a billing-provider protocol and an explicitly non-production development stub that refuses checkout with no database side effects; staging/production reject stub configuration.
- Added authenticated account aggregation for subscription state, entitlements, active device sessions, plans, and billing capability.
- Added owned device revocation, sign-out-other-sessions, and current-password-verified rotation that revokes other sessions while retaining the current device.
- Added a responsive Account & Access dashboard with profiles, truthful subscription/billing states, plan catalog, device security, and password controls.
- Added API and desktop/mobile browser acceptance for multiple devices, revocation, password rotation, new credential verification, and no fake payment behavior.
- Closed Phase 10 with 28 browser tests, 10 API tests, production build, lint, types, unit tests, dependency audit, migration roundtrip/drift check, live readiness, and responsive visual review passing.

### Phase 9 — Homepage Manager and Scheduling (Pass)

- Added relational homepage drafts with hero selection, editorial/query rails, manual pins, enablement, UTC rail windows, and deterministic ordering.
- Added private draft preview and atomic published snapshots so incomplete Studio edits cannot affect the live customer page.
- Replaced the hard-coded customer layout with published hero/rail resolution while retaining an honest catalog fallback before the first homepage publication.
- Added timezone-required movie/series publication and rights windows, database constraints, automatic due publish/unpublish transitions, and Studio scheduling forms.
- Added authenticated/audited homepage APIs and customer filtering for publication state, rights availability, schedule visibility, query source, and duplicate titles.
- Added desktop/mobile browser acceptance proving source-free Studio layout changes, plus API coverage for UTC validation, state automation, rights exclusion, preview, and draft/live isolation.
- Resolved a DOM-test dependency incompatibility by pinning jsdom 26.1.0 and deduplicating Vitest's peer graph for the supported local Node runtime.
- Closed Phase 9 with 26 browser tests, 9 API tests, production build, lint, types, unit tests, dependency audit, migration roundtrip/drift check, live readiness, and responsive visual review passing.

### Phase 8 — Production-Grade Player and Progress (Pass)

- Added persistent movie/episode playback assignments, Ready-job integrity rules, optional intro/recap/credits markers, and profile-scoped progress through a reversible, drift-free migration.
- Added authenticated playback configuration and protected manifest, playlist, subtitle, and range-capable segment delivery without leaking storage credentials or keys.
- Added an HLS.js customer player with adaptive/manual quality, audio/subtitle selection, core controls, fullscreen, picture-in-picture, playback speed, keyboard and Media Session integration, skip actions, next episode, and recoverable states.
- Added validated ten-second progress persistence, pause/page-exit saves, completion calculation, and reliable leave/return resume for the active profile.
- Added Studio assignment controls and real customer Play availability for assigned published titles.
- Tightened parallel browser-test isolation around upload rows and classified HLS segment cancellation during navigation as an expected abort.
- Closed Phase 8 with 24 browser tests, 8 API tests, production build, lint, types, unit tests, dependency audit, migration roundtrip/drift check, live readiness, and desktop/mobile visual review passing.

### Phase 7 — Media Processing (Pass)

- Installed FFmpeg 9.0.1 and added a Redis-backed, independently running media worker.
- Added persistent processing jobs with queued/probing/processing/validating/ready/failed states, progress, attempts, source metadata, tracks, chapters, renditions, derived assets, outputs, and errors.
- Added FFprobe codec/container inspection, source-aware H.264/AAC renditions, HLS packaging, subtitle extraction, thumbnails, preview sprites, and stable MinIO output prefixes.
- Added strict playlist, segment, master-manifest, and FFprobe playback validation before Ready.
- Added an auto-refreshing responsive Studio Processing dashboard with observable stages, source/rendition detail, errors, and retry.
- Added generated-video integration and browser acceptance coverage proving upload → queue → background worker → playable adaptive manifest at desktop/mobile sizes.
- Fixed a hydration race in file selection revealed by the full parallel browser suite by keeping the input unavailable until the Client Component is interactive.
- Closed Phase 7 with 22 browser tests, 7 API tests, production build, lint, types, unit tests, dependency audit, migration roundtrip/drift check, live readiness, and visual review passing.

### Phase 6 — Upload System (Pass)

- Added the MediaAsset lifecycle and a reversible, drift-free PostgreSQL migration.
- Added authenticated initialization with UUID-derived keys and short-lived signed direct-to-MinIO PUT URLs.
- Added chunked browser SHA-256 calculation, transfer progress, cancellation, failure reporting, retry state, and completion verification.
- Added server checks for allowlisted media types, maximum size, unsafe filenames, object length, checksum metadata, full stored SHA-256, and MP4/WebM/QuickTime signatures.
- Added an operational responsive Studio Uploads registry; object-storage credentials and local paths remain server-only.
- Added API and desktop/mobile browser acceptance coverage proving a permitted source reaches both PostgreSQL and MinIO, plus negative validation and lifecycle cases.
- Closed Phase 6 with 20 browser tests, 6 API tests, production build, lint, types, unit tests, dependency audit, migration roundtrip/drift check, readiness, and visual review passing.

### Phase 5 — Admin Studio CMS (Pass)

- Replaced the Studio placeholder with an operational dashboard and navigation whose future areas are explicitly labeled rather than exposed as dead destinations.
- Added a searchable/filterable content library with lifecycle badges and edit, preview, publish, and unpublish controls.
- Added authenticated browser movie creation/editing, artwork metadata, private draft previews, and public-visibility lifecycle controls.
- Added authenticated browser series creation with ordered seasons, individual episodes, bulk episode rows, and private hierarchy previews.
- Added development-restricted PostgreSQL fixture inspection/cleanup and four desktop/mobile Studio acceptance cases.
- Fixed parallel browser-fixture isolation and exact form targeting uncovered during acceptance testing.
- Closed Phase 5 with 18 browser tests plus API lint/tests, web build/types/lint/unit tests, dependency audit, live readiness, and responsive visual review all passing.

### Phase 4 — Customer Catalog UX (Pass)

- Replaced the static customer shell with a server-rendered, backend-driven featured film and movie/series rails.
- Added reusable accessible content cards and responsive movie/series library routes.
- Added dynamic movie details with available metadata, credits, related-title state, and honest media/My List availability.
- Added dynamic series details with a client-interactive season selector, ordered episodes, and explicit not-started/playback states.
- Added title, people, genre, and tag search with prompt and no-result experiences.
- Added streamed skeletons, empty/error/404 states, reduced-motion behavior, responsive layouts, and keyboard/touch affordances.
- Corrected the seeded release date after visual QA exposed a published title labeled “Coming soon.”
- Added four desktop/mobile live-catalog Playwright cases; all 14 browser regressions pass without critical console or failed-request events.
- Closed Phase 4 after successful API tests/lint, web typecheck/lint/unit tests, production build, dependency audit, live readiness, and desktop/mobile visual review.

### Phase 3 — Catalog Domain (Pass)

- Added persistent ORM mappings for the complete Phase 3 entity list.
- Added normalized movie/series taxonomy associations, hierarchy ownership, lifecycle enums, foreign keys, uniqueness rules, exactly-one-parent checks, and catalog query indexes.
- Added typed schemas, transactional services, protected/audited administrator CRUD, and published-only customer reads/search.
- Added an idempotent development-only original catalog seed for one movie and one episodic series.
- Found and fixed orphaned PostgreSQL enum types during rollback; verified downgrade, clean re-upgrade, zero Alembic drift, and reseeding.
- Added integration coverage for normalized metadata, draft isolation, publishing, search, credits, artwork, previews, series hierarchy, validation, and database constraints.
- Closed the Phase 3 gate with all API, web, browser, dependency-audit, and live-readiness regressions passing.

### Phase 2 — Authentication, Admin Provisioning, and Profiles (Pass)

- Added separate customer/admin identities and database-backed session models with Argon2id passwords and hashed opaque tokens.
- Added customer registration/login/logout and profile CRUD/switch APIs with viewer preferences.
- Added Redis login throttling, trusted-origin checks, secure cookie policies, session revocation, and admin audit logs.
- Added an interactive single-administrator provision/rotation command with no public admin registration endpoint.
- Added the private Studio login page, Next.js Proxy prefilter, and secure render-time API authorization.
- Added responsive customer registration, login, password recovery, password reset, and profile-selection journeys.
- Added encrypted TOTP enrollment/challenge support and hashed one-use administrator recovery codes.
- Added one-use expiring password-reset tokens, all-session revocation, development reset links, and production SMTP configuration enforcement.
- Added integration and browser tests proving customer/admin isolation, profile switching, password reset, unauthorized Studio blocking, and authorized Studio login across desktop and mobile.
- Corrected Chromium reset-request completion semantics by returning an explicit JSON success response and closed the Phase 2 acceptance gate with all checks passing.

### Phase 1 — Live Foundation

- Added the Next.js customer and Studio shells with a responsive cinematic design foundation.
- Added the FastAPI service, typed environment configuration, health/readiness checks, PostgreSQL model base, and initial Alembic migration.
- Installed and connected PostgreSQL, Redis, and MinIO; created the development storage bucket.
- Added frontend unit testing, linting, strict type checks, backend tests, and backend linting.
- Started the full local stack with frontend/backend hot reload and verified all service endpoints over HTTP.
- Added Playwright desktop/mobile acceptance tests with console, page-error, and failed-request gates.
- Added real mobile navigation patterns to the customer and Studio shells after visual inspection exposed hidden navigation.
- Browser-verified both shells and closed Phase 1 with no console or request failures.
- Upgraded Playwright to the patched 1.62.1 release and verified `npm audit` reports zero vulnerabilities.

### Phase 0 — Repository Audit and Control Package

- Audited the greenfield workspace.
- Added the required architecture, development, status, product-decision, and changelog documents.
- Added the initial environment-variable contract without secrets.
# 2026-08-17 — Public catalog design and discovery pass

- Added shared, metadata-rich public catalog cards with correct portrait artwork, season/episode facts, genres, ratings, runtime, and ongoing status.
- Added `/browse`, `/new-releases`, `/currently-airing`, `/recently-updated`, and `/trending` discovery pages.
- Labeled Trending as an editorial spotlight until sufficient first-party activity exists for an honest behavioral ranking.
- Added Browse, New, and Airing navigation destinations.
- Added global route loading skeletons and recoverable error UI with reduced-motion support.
- Preserved conditional Dub/Sub rendering: language badges are shown only when verified media-track data exists.
- Verified TypeScript, ESLint (zero errors), 14 web tests, policy validation, and a 44-route production build.
# 2026-08-17 — Global TMDB catalog expansion

- Reworked the TMDB importer with `anime`, `global`, and balanced `mixed` discovery scopes.
- Added round-robin discovery across US/English, Korean, Indian/Hindi, French, Spanish-language, and Chinese-language markets, plus documentary, horror, and science-fiction slices.
- Imported 30 global movies and 24 global series locally without removing the existing anime catalog.
- Expanded public catalog fetch limits to 100 so the worldwide selection is visible on Home, Movies, and Series.
- Updated homepage collection labels from anime-only wording to worldwide movie and series discovery.
# 2026-08-17 — Removed leaked recommendation fixtures

- Removed 12 synthetic `Recommendation Watched/Similar/Popular` movie records from the local catalog.
- Customer movie list and detail endpoints now permanently exclude the recommendation test-fixture slug namespace, including after interrupted test cleanup.
- Expanded the audit and safeguard to all confirmed movie-fixture namespaces: playback, analytics, curation, clubs, community, scene processing, catalog relations, and recommendations.
# 2026-08-17 — Ordered franchise marathon rails

- Imported and pinned 46 verified TMDB movie placements across four homepage marathons.
- Added Saw I–X, the MCU Infinity Saga through Endgame, Mission: Impossible, and Middle-earth in intentional watch order.
- Added ominous/editorial rail copy, horizontal poster carousels, and numbered chapter badges so order is clear.
# 2026-08-17 — Progressive Instant Results

- Limited the homepage Instant Results grid to nine initial cards.
- Added incremental “Show 9 more,” result progress, and smooth “Show less” controls.
- Filters continue to evaluate the full catalog regardless of how many cards are currently visible.
- Replaced downward expansion with in-place nine-title pages, previous/next arrows, directional swoosh transitions, page ranges, and progress indicators.
# 2026-08-17 — Persistent client library and playback fallback

- Added device-persistent recent views, searches, saved titles, liked titles, and playback positions using versioned local storage.
- Added Like/Save controls to movie and series detail pages and a `/activity` dashboard.
- Added playback-position fallback so interrupted server saves can still resume on the same device.
- Preserved authenticated server progress and profile My List as authoritative cross-device state.
# 2026-08-18 — Hostinger production-target migration

- Replaced DigitalOcean as the active production target with a Hostinger VPS Compose stack.
- Added Caddy HTTPS ingress, API/web/workers, PostgreSQL, authenticated Redis, private versioned MinIO, and ClamAV services with no database/cache/scanner public ports.
- Added a labeled git-ignored dummy credential file and fail-closed deploy validation.
- Added Hostinger operations profiles and a guarded runner for production preflight, five-minute maintenance, and daily off-site PostgreSQL backups with manifest integrity metadata.
- Added an immutable-image Hostinger rollback controller with read-only inspection, exact execution confirmation, local image verification, atomic mode-preserving tag changes, `--no-build` deployment, production preflight, automatic tag restoration on failure, and credential-redacted errors.
- Added a separate ignored restore input, fail-closed pre-container validation, and a guarded isolated-restore operation using the existing checksum/migration/table-parity verifier.
- Added explicit CPU, memory, PID and bounded log ceilings across the Hostinger stack, hardened read-only/capability-free runtimes, health checks, unprivileged internal Caddy ports, and a rendered-topology security auditor.
- Closed direct-origin bypass with a separate edge-to-origin credential that the trusted geo Worker strips and reinjects; Hostinger Caddy returns 404 without it.
- Added guarded hourly media mirroring to a distinct private/versioned HTTPS S3-compatible destination without destructive remote deletion, plus capacity-headroom and replication validators.
- Added a read-only, stable-JSON Hostinger host auditor covering OS, hostname, capacity, time, services, effective SSH, UFW, Docker daemon policy, and encrypted-volume evidence.
- Added an explicit-confirmation VPS bootstrap that refuses dummy/broad SSH inputs, requires the current SSH source to match the allowlist, validates sshd before reload, and applies automatic updates, Fail2ban, defense-in-depth firewall, SSH key-only policy, and Docker daemon hardening. No workstation or provider host was mutated.
- Added the host-access/capacity incident runbook.
- Added private Node Exporter and Prometheus services with no published ports, authenticated API scraping, bounded retention, and an atomic mode-0600 credential-last configuration renderer.
- Added stable host-audit gauges and atomic allowlisted success timestamps for maintenance, backup, preflight, restore, and off-site media replication.
- Added host-audit, disk-pressure, clock-sync, stale-backup, stale-replication, and stale-maintenance alert rules while keeping real receivers and notification evidence explicitly external.
- Added private Blackbox Exporter probes for web security headers, API readiness, storage health, CDN reachability, direct-origin denial, and TLS expiry, with credential-last HTTPS target rendering and structural coverage validation.
- Replaced mutable VPS-built release tags with full API/web/backup registry digest references across every Hostinger application and operation service; production Compose contains no application build contexts.
- Added an approved-builder release script, literal dotenv reader, atomic digest pinning, three-digest rollback, and backup-image inclusion in the launch-evidence contract.
- Added a complete Hostinger evidence map for every launch-evidence kind, separating repository procedures from owner/provider/legal artifacts.
- Restored Colima and the isolated HTTPS staging stack; current web and API readiness pass. Validated the real Caddy configuration, Prometheus config plus all 17 rules, and Blackbox probe configuration with their pinned container binaries.
- Selected Hostinger New York because Hostinger does not provide a Toronto VPS location.
- Updated the production handoff, launch checklist, geo/CDN edge, private Studio, and public-edge documentation to identify Hostinger as the active origin.
- Kept production NO-GO: the Hostinger account, DNS/TLS, secrets, off-site recovery, rollback rehearsal, alert receivers, administrator enrollment, licensed catalog, and policy approvals remain unverified.
- Rechecked live state rather than inheriting stale claims: hot-reload web is HTTP 200, API readiness returned to healthy after restarting local MinIO, while Docker/Colima and the isolated HTTPS staging stack remain stopped.
- Fixed Hostinger Caddy admission ordering after the final adapted-config audit proved standalone directives could be sorted behind proxy handlers.
- Replaced the unconditional Studio denial with a second-secret condition: every application request requires the trusted origin-edge header, while `/studio` and `/api/admin` also require the private Studio gateway header.
- Added a real adapted-JSON policy validator and regression tests proving both secret matchers exist and both denial routes execute before application proxy routes.
- Added a repeatable real-Caddy ingress acceptance gate covering direct-origin denial, trusted public homepage/API admission, public Studio/admin denial, and two-secret private Studio/admin admission against the running staging upstreams.
- Replaced per-item homepage snapshot reads with two bulk pinned-title queries, reducing the 46-placement franchise homepage from 52 SQL statements back under its six-statement ceiling.
- Kept synthetic-fixture suppression on discovery surfaces while restoring exact-title and knowledge-graph behavior, and updated stale catalog/billing/Studio-navigation acceptance assumptions.
- Re-ran the broad gate: Ruff, 86 API tests, TypeScript, ESLint without errors, 15 web tests, the 45-page production build, and six desktop/mobile homepage/security/performance journeys pass.
- Added shared responsive poster delivery for homepage rails, catalog cards, and Instant Results, selecting TMDB CDN widths of 185/342/500 pixels while preserving lazy loading, intrinsic sizing, and direct delivery for non-TMDB artwork.
- Extended the desktop/mobile loading-budget journey to assert the actual poster `srcset` and `sizes` contract; both viewport checks pass after the optimization.
- Extended responsive edge-sized artwork to activity, search, external discovery, movie/series details, and episode stills; above-fold imagery is prioritized while all list imagery remains lazy.
- Preserved owner/private image URLs byte-for-byte instead of rewriting or proxying them, covered by dedicated image URL tests.
- Removed all remaining raw-image lint warnings and refreshed stale catalog acceptance copy/selectors; 17 web tests, the production build, two desktop/mobile performance checks, and four desktop/mobile catalog journeys pass.
