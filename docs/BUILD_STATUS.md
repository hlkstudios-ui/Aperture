# Build Status

Last updated: 2026-08-30

PHASE: 31 — Production Launch Gate

STAGE: Final evidence audit and owner/infrastructure handoff

STATUS: LOCAL PRODUCT AND HOSTINGER CONTROL PACKAGE COMPLETE — HOT-RELOAD DEVELOPMENT AND HTTPS STAGING RUNNING; PUBLIC PRODUCTION REMAINS NO-GO ON 6 EXTERNAL BLOCKERS

IMPLEMENTED:
- Promoted Caddy, MinIO storage, Node Exporter, and Blackbox Exporter from mutable upstream runtime
  selections to first-party Hostinger release artifacts. The approved builder now compiles their
  exact reviewed sources with patched dependencies into pinned nonroot distroless images, pushes
  them beside API, media-worker, web, and backup, and atomically records all eight distinct
  digests. Compose, sanitized VPS rendering, topology validation, rollback, and the nine-binding
  launch record carry all four new artifacts end to end; the Scene worker remains bound to API.
  Local no-push Caddy 2.11.4, MinIO storage, Node Exporter 1.12.1, and Blackbox Exporter 0.28.0
  scans each report 0 critical/0 high findings. Prometheus 3.14.0-distroless validates the current
  scrape configuration and all 17 rules, and the first-party Blackbox binary validates every
  current probe module.
  Registry push, provider pull, retained release scans, and live rollback remain external evidence.
- Added fail-closed Caddy guards for the still-applicable upstream MinIO application advisories.
  Before a request can reach storage, the ordered route rejects unsigned-payload trailers,
  Snowball auto-extract metadata, S3 Select, replication server-side-encryption metadata, and the
  internal storage REST namespace. The adapted-policy validator proves every denial precedes the
  MinIO proxy, and a real hardened Caddy/storage integration smoke returned the expected 403/404
  responses while normal readiness and signed S3 create/version/put/get operations passed. These
  are explicit edge mitigations, not a claim that the final Community source contains upstream
  application fixes.
- Upgraded the live private Studio gateway on the Hostinger VPS to the same locally audited Caddy
  candidate digest. It runs nonroot, read-only, capability-free, and loopback-only on
  `127.0.0.1:8080`; Tailscale Serve presents it only inside the tailnet and the container has no
  restarts. The VPS is tagged `tag:aperture-studio`, the default allow-all tailnet policy has
  been replaced by an owner-only TCP 443 grant, and node-key expiry is disabled for the
  unattended server. Public application traffic and the application upstream remain unopened, so
  the Serve authorization is infrastructure readiness rather than a completed Studio UI launch;
  owner-device access, administrator provisioning, and MFA acceptance are still gates.
- Split the Hostinger Python release into a FFmpeg-free API image and a distinct audited media
  worker image while retaining Python 3.12.14 on Alpine 3.24. API, migration, Scene worker,
  maintenance, and preflight remain on one immutable API digest; only media processing receives
  the FFmpeg image. Source/runtime allowlists, Compose topology, validation, approved-builder
  pinning, eight-artifact rollback, security-scan evidence guidance, and atomic credential handling
  now carry the worker digest end to end. Local no-push builds prove the API lacks FFmpeg/FFprobe
  and the worker supplies FFmpeg 8.1.2; both run as `aperture` on Python 3.12.14. Docker Scout
  reports 0 critical/0 high findings for the API and 0 critical/16 high findings for the worker:
  11 FFmpeg, two libsndfile, and two cJSON findings currently have no Alpine fix, while the one
  libvpx fix is not available from the pinned Alpine 3.24 repositories. The eventual immutable
  registry artifacts still require fresh retained scans before deployment.
- Consolidated all owner-entered application and Hostinger deployment credentials into the
  repository-root mode-0600 `.env`. Hostinger Compose/operations, release pinning and rollback,
  host hardening, monitoring, isolated restore, and the private Studio gateway now consume that
  single source; redundant per-folder local dotenv files were removed. The committed
  `.env.example` retains the complete labeled template, while provider-specific examples remain
  non-secret documentation/test fixtures. SSH private-key material is deliberately excluded in
  favor of a local key-path label. The consolidated template has 196 unique labels with no
  duplicates; current Hostinger/private-Studio dummy validation, shell parsing, and all 11 private
  gateway tests pass.
- Completed the customer image-delivery audit. Activity history, global TMDB results, universal search, movie/series detail posters and backdrops, episode stills, homepage rails, catalog cards, and Instant Results now use shared responsive CDN candidates with correct intrinsic geometry, `sizes`, decoding, and above-/below-fold priority. TMDB performs resizing at its own edge; owner/private URLs are never rewritten or proxied through Hostinger. All raw-image lint warnings are eliminated. Two transformation/privacy tests were added, and stale catalog browser assertions were aligned with the current global homepage, slideshow, search heading, and unique related-match semantics. TypeScript and ESLint are clean, 17/17 web tests and the 45-page production build pass, loading budgets pass at desktop/mobile, and the complete focused catalog journey passes 4/4 at desktop/mobile with clean console/network gates.
- Optimized high-traffic poster delivery for slow connections without proxying third-party artwork through the Hostinger VPS. Homepage rails, catalog cards, and Instant Results now share a responsive poster component that asks TMDB's image CDN for 185 px, 342 px, or 500 px artwork according to the rendered card width; non-TMDB sources retain their original URL. Lazy loading, asynchronous decoding, intrinsic dimensions, and the existing below-fold content-visibility boundary remain intact. Desktop/mobile browser acceptance proves the responsive `srcset`/`sizes` contract and stays within loading, resource, and script-transfer budgets; TypeScript, ESLint with no errors, 15/15 web tests, and the 45-page production build pass.
- Closed regressions found by the post-Hostinger full gate. The 46 pinned franchise placements had changed `/homepage` into a 52-statement N+1; pinned hero/rail movie and series records are now collected and loaded in at most two bulk queries, restoring the six-statement homepage ceiling. Fixture suppression remains on discovery lists/search but no longer breaks exact-title and knowledge-graph routes. The catalog test no longer uses a deliberately suppressed slug, billing settings tests explicitly isolate CAPTCHA inputs, and the browser foundation test now asserts that private Studio has no public navigation link before checking direct-route protection. Ruff, 86/86 API tests, TypeScript, ESLint with no errors, 15/15 web tests, the 45-page production build, and 6/6 desktop/mobile homepage/security/performance browser checks pass.
- Corrected a final Hostinger ingress audit defect before handoff: Caddy's directive sorting could place application proxies ahead of standalone denial directives, and the previous Studio denial was unconditional. The application policy now uses an order-preserving `route`: a valid origin-edge secret is required for every web/API request, and `/studio` plus `/api/admin` additionally require the private Tailscale Studio-edge secret. The first-party Caddy 2.11.4 adapted JSON is checked for both matchers and denial-before-proxy order. A repeatable runtime gate also exercises that production Caddyfile against the running staging API/web: direct requests and public Studio/admin receive 404, trusted homepage/API requests pass, and two-secret private Studio/admin requests reach their upstreams. Caddy validation, rendered topology validation, Ruff, the current focused Hostinger policy tests, and all 10 private-gateway tests pass.
- Completed the post-migration Hostinger evidence audit. `docs/HOSTINGER_EVIDENCE_MAP.md` maps every required launch-evidence kind to the exact repository verifier/procedure and the owner/provider/legal artifact still required. The actual first-party Caddy 2.11.4 binary validates the origin/security configuration, Prometheus 3.14.0-distroless `promtool` validates its config plus all 17 alert rules, and the first-party Blackbox Exporter 0.28.0 binary validates all probe modules. The isolated HTTPS staging stack is running again: customer edge returns 200 and API readiness reports PostgreSQL, Redis, and object storage healthy. No known repository-owned gap remains in the focused audit, but all six production gates remain external and production is still NO-GO.
- Closed a final-audit release-integrity gap in the Hostinger target: production no longer builds on the VPS or uses mutable local `IMAGE_TAG` values. Every first-party API/web/worker/migration/operation/backup/restore/Caddy/storage/exporter service is pinned to a full registry `@sha256` reference and topology validation rejects build contexts or mutable tags. A credential-safe approved-builder script pushes explicit non-`latest` linux/amd64 releases, resolves registry manifest digests, and atomically pins the eight-artifact API/media-worker/web/backup/Caddy/storage/node-exporter/Blackbox release without sourcing dotenv as shell code. Rollback verifies and atomically switches that exact set and reports only digests; the nine-component launch record binds the Scene worker to the API digest. Real registry build/push/pull remains external evidence.
- Hardened that publisher and rollback contract further. Publishing now rejects unpublished source
  changes before any Docker or registry operation, atomically reserves a one-use release ID,
  proves all eight exact tags absent, emits SBOM/provenance attestations, and commits a secret-free
  manifest/checksum before pinning the owner environment. Storage-image rollback requires recorded
  compatibility, snapshot, and clone-rehearsal confirmations. A Caddy rollback or automatic
  compensation updates, redeploys, and verifies both the public edge and private Studio gateway;
  failure stages remain structured and secret-free.
- Added private Blackbox Exporter coverage without opening host ports. Credential-last rendering creates exact HTTPS targets for public web security headers, `/api/ready` body, storage readiness, CDN TLS reachability, and direct Hostinger origin 404 denial; Prometheus relabeling selects the corresponding fail-closed module. Alerts cover any probe/security/origin-contract failure and TLS certificates inside 14 days. A structural validator proves all five unique surfaces use HTTPS, reference defined modules, bind origin to the denial module, keep API scraping authenticated, and include every Hostinger alert. The first-party 0.28.0 binary validates the current modules. Live public DNS/TLS probes and multi-region evidence remain unclaimed.
- Extended Hostinger production observability with private, no-host-port Prometheus and Node Exporter services, bounded 15-day/10-GB retention, authenticated API scraping, host metrics, and an atomic mode-0600 scrape-config renderer that rejects dummy deploy credentials. Host audit writes stable per-check gauges; successful maintenance, backup, preflight, restore, and media replication write allowlisted atomic freshness timestamps only after command success. Added critical alerts for missing/failing host audit, root disk below 15%, unsynchronized clock, backup older than 30 hours, media replication older than three hours, and maintenance older than 15 minutes. Prometheus 3.14.0-distroless `promtool` validates the current configuration and all 17 rules. Live production scraping and real receiver delivery remain unverified.
- Added a Hostinger host-level control package with labeled ignored inputs, narrow CIDR validation, explicit apply confirmation, and a stable secret-free read-only audit covering Ubuntu 24.04, exact hostname, provider-labeled capacity with bounded guest-visible provisioning overhead, free space, time synchronization, automatic updates, Fail2ban, Docker, effective sshd policy, normalized exact-CIDR UFW rules, Docker live restore/no-new-privileges/log rotation, and encrypted-volume evidence. The apply path installs an early-sorting managed SSH drop-in, removes the obsolete later-sorting Aperture file, and verifies effective `sshd -T`. It also pre-seeds a jail-specific late-sorting Fail2ban override that exempts only loopback and the validated operator CIDR from sshd bans, syntax-checks before restart, and preserves protection for every other source. Real KVM4 observations of 15 GiB RAM and 193G root disk pass the unchanged 16/200 provider contract; below 15/190 still fails closed.
- Hardened the Hostinger single-VPS topology with explicit CPU/memory/PID ceilings, a validator-enforced 20% host-memory reserve, bounded JSON log rotation, read-only/no-new-privileges/capability-free application and operation containers, unprivileged internal Caddy ports, and health checks for every persistent request/dependency service. Only Caddy publishes host ports. Added a separate geo-edge-to-origin admission secret so direct web/API origin requests fail with 404; spoofed client copies are removed at the Worker. Added guarded hourly private/versioned off-site media mirroring that refuses dummy, HTTP, loopback/in-VPS, or same-bucket destinations and never deletes replica objects. Topology rendering/audit, Ruff, shell syntax, configuration validation, geo-edge tests, and current first-party runtime-image/Caddy validation pass. The public production stack and provider acceptance remain unclaimed.
- Added Hostinger-specific rollback and recovery controls. Rollback inspect verifies the exact local API/media-worker/web/backup/Caddy/storage/node-exporter/Blackbox digest set; execute requires an exact confirmation, atomically changes only those eight image references, uses `--no-build`, runs production preflight, and automatically restores the previous digest set after startup/preflight failure without claiming database rollback. The isolated restore path requires a new `aperture_restore_*` database, exact confirmation, HTTPS backup origin, non-dummy read-only inputs, manifest/dump binding, checksum, migration-head, and table-count parity. Live provider rollback/restore remain external evidence.
- Migrated the active provider contract to Hostinger Boston 2 with explicit capacity profiles: recommended `full` KVM 8 (32 GiB RAM, 8 vCPU, 400 GiB disk) and guarded `compact` KVM 4 (16 GiB RAM, 4 vCPU, 200 GiB disk) for the owner's approved wipe-and-reuse target. Compact retains stricter memory headroom and lower service ceilings rather than bypassing validation. The VPS and Cloudflare zone now exist and the host hardening plus private Studio gateway are live, but the production Compose application stack, public routes/TLS acceptance, off-site backup, and rollback rehearsal remain unclaimed.
- Added an immediate, client-side homepage catalog browser with left-side type/country/duration/studio/genre filters and a responsive right-side results grid. Studio and format values are persisted source metadata, including an explicit keyword-backed OVA import slice; no OVA classification is fabricated from generic series data.
- Refined the slideshow presentation with clear near-full-opacity artwork, a copy-safe cinematic gradient, richer per-title context, centered numbered progress, edge-mounted left/right navigation, and responsive mobile controls. Only the active high-resolution backdrop loads, retaining the earlier bandwidth boundary.
- The homepage hero is now an accessible automatic slideshow capped at ten entries, balancing five latest movies with five currently ongoing series and ordering the combined set by release date. It includes manual navigation, pause-on-interaction, reduced-motion handling, correct movie/series links, and active-slide-only backdrop loading. TMDB ongoing status persists through migration `20260817_0023`; the live homepage renders ten controls with seven eligible ongoing series in the current catalog.
- Populated the local customer catalog from TMDB with 16 anime films and 16 anime series, provenance-safe stable IDs, high-resolution poster/backdrop URLs, normalized metadata, series season shells, a published two-rail homepage, and visible TMDB attribution. The importer is repeatable and restricted to development/test; imported metadata does not imply streaming rights and is excluded from playback recommendations. Migration `20260817_0022`, zero drift, 84/84 API tests, Ruff, TypeScript, ESLint, production build, live homepage SSR, and image delivery pass.
- Completed the owner-requested local finish audit. A repeated deployed browser run exposed duplicate forced playback-progress writes during navigation: `pagehide` and React teardown could issue the same request, allowing Chromium to cancel one and surface a misleading CORS console failure despite the API returning 200 for the surviving request. Forced lifecycle persistence now de-duplicates sub-quarter-second saves and uses a bounded fetch keepalive. The focused desktop adaptive-player journey passed, followed by the complete 46/46 enabled-feature desktop/mobile HTTPS matrix. API Ruff and 84/84 tests, web TypeScript/ESLint and 14/14 tests, CDN 4/4, geo edge 2/2, production build, migration head/drift, and both development/staging readiness checks pass.
- Refreshed the current local production-shaped evidence after the free-tier handoff: immutable API/web images rebuilt successfully, migrations and the isolated seed completed, dependency readiness passed, and the deployed HTTPS Playwright matrix passed 46 enabled-feature journeys with four intentionally skipped all-flags-off cases. A new isolated backup restored at `b7e4c91d2a60` with 91/91 public tables, and the credential-free public-edge verifier passed all six staging checks.
- Added a separate public free-tier staging target under `deploy/staging/free-tier` without changing the DigitalOcean Toronto production target. It defines two sleeping Render Free web services, Supabase-compatible TLS PostgreSQL, TLS Redis, private Cloudflare R2, Sentry, SMTP, labeled ignored credentials, dummy/deploy validation, and a fail-together supervisor for the API/media/scene processes. This is explicitly a low-traffic demo topology: free-tier quotas, co-located workers, sleep behavior, absence of Toronto placement/HA/production recovery evidence, and content/legal ownership remain disclosed and do not reduce the six production blockers.
- Territory-rights local implementation is complete: signed viewer-country assertions and migration `b7e4c91d2a60` provide the trusted signal and explicit movie/series/edition allowlists; Studio exposes every scope; enforcement spans catalog, homepage, recommendation/prescription, knowledge/credits, curation, community, clubs/parties, SceneLens/Cinephile, progress, playback leases, and API/CDN media. CDN signatures/caches are country-bound, and a deployable web/API geo edge strips spoofed values and signs provider-derived country. Real edge deployment, DNS/origin binding, and public multi-country acceptance remain external, so production regional-rights completion is not claimed.
- Completed Phase 30 with isolated PostgreSQL/Redis/MinIO/Mailpit, separate random staging secrets, loopback staging DNS, Caddy HTTPS, immutable API/web images, one-shot migrations, independent workers, protected Studio, and production-like private media delivery.
- Phase 30 acceptance: 42/42 deployed Chromium desktop/mobile journeys pass over HTTPS, including real upload/transcode/adaptive playback, SceneLens, private watch parties, exact subscription/entitlement state, unavailable-billing honesty, and SMTP-delivered one-use password reset.
- Phase 31 added operational Studio MFA enrollment, one-time recovery codes, administrator sign-out, staging database/config backup, isolated restore verification, MinIO object versioning, and an expanded Chromium mobile/tablet/laptop/large-desktop plus Firefox/WebKit matrix.
- Phase 31 closed the remaining code-owned Studio placeholder: Users now supports authorized search/detail, safe export, audited reason-gated account state and session revocation; Subscriptions exposes provider-authoritative operational state; Storage exposes inventory, health, versioning, and failure state without secrets.
- Completed the Command A customer-data workflow with a versioned portable export spanning account, preferences, viewing, SceneLens memory, analytics, curation, community, sessions, subscription, payment-summary, and entitlement records while excluding credentials and provider references. Permanent deletion is four-factor confirmed, cascade-backed, and retains only a non-identifying administrator audit tombstone.
- Fixed the completion-audit regressions found by deployed acceptance: support tables now scroll with reachable 44 px actions on mobile, document locale responses are private/no-store and vary by session cookie, and community acceptance targets the immutable seeded title rather than a concurrently deleted test fixture.
- Phase 31 browser evidence passes across all six viewport/engine profiles; generated adaptive playback, subtitles, resume, SceneLens, and QoE also pass in Firefox and WebKit.
- Current support acceptance passes 84/84 API regressions and 46/46 deployed enabled-feature desktop/mobile Chromium journeys on migration `b7e4c91d2a60`; the separate all-risky-features-off deployed matrix passes 4/4. Production build, TypeScript, ESLint, Ruff, 14 Vitest checks, CDN/geo-edge tests, and migration drift checks pass.
- `docs/LAUNCH_CHECKLIST.md` records a NO-GO with six unresolved external production blockers. No production launch has been attempted or implied.
- Protected CDN delivery is locally complete: the API issues five-minute session/source HMAC grants, a deployable edge validates before cache lookup, secret-origin misses revalidate current rights, and ranges bypass cache. The regression set passes four edge tests, web TypeScript/ESLint/Vitest, the 42-route production build, and the dummy DigitalOcean renderer.
- Added typed, environment-specific server and web feature flags for SceneLens, Ask This Movie, Community, watch parties, and experimental recommendations. Parent domains remove customer routers/navigation/pages; independently disabled Ask/party controls disappear and their server actions fail closed.
- Added a secret-free launch-evidence contract and verifier covering the six external blockers. It binds exact release/image/migration/infrastructure identity to named owners, approvals, timestamps, and required evidence classes; rejects dummy/secret-like/incomplete/self-approved production records; and can never replace human approval. The labeled dummy record validates as `no_go` with all six gates remaining.
- Added the complete legal-policy publishing boundary for eight required documents. Owner-pending documents are neither linked nor served; approved version/effective-date/sections render through accessible routes and a global footer. Production builds and DigitalOcean deploy mode fail closed until the tracked policy package contains approved, non-placeholder, substantive content and the owner explicitly enables the gate.
- Added explicit per-profile optional analytics consent, default-off ingestion enforcement, UTC consent-change evidence, transactional raw-event erasure on withdrawal, and account privacy controls separating necessary resume progress from optional analytics. No Algorithm now also removes watch-history and explicit-preference ranking from Discover and discloses its editorial/aggregate-only strategy.
- Added a fail-closed master-upload malware boundary. Objects remain non-processable until a persisted scanner verdict is clean; deterministic EICAR tests cover clean/detected/outage/retry behavior over real MinIO, and the production ClamAV INSTREAM/PING adapter is protocol-tested. Studio visibly distinguishes pending quarantine, scanner outage, clean and infected verdicts, preserves the backend quarantine after a post-transfer outage, and offers a scan-only retry. Production configuration requires a private clamd endpoint and preflight verifies it without scanning or mutating content.
- Enforced plan/account simultaneous-stream limits instead of merely displaying them. Playback configuration atomically acquires an expiring Redis lease per device session, active media refreshes but cannot mint a lease, invalid/missing entitlement data fails closed to one stream, stale devices recover automatically, and Redis failure denies admission. Production lease lifetime covers the complete CDN grant lifetime, and watch pages expose an actionable limit/coordination state instead of a generic server error. The generated adaptive-playback acceptance now opens a second authenticated browser device and proves denial plus recovery guidance on desktop and mobile while the first stream continues.
- Completed flag-off HTTP acceptance against an isolated production build: the homepage remained 200 with disabled navigation absent, while Community, Clubs, Discover, Prescription, and party paths returned true 404 responses. A first implementation exposed Next.js streamed not-found bodies as 200; the request proxy now enforces the status before rendering.
- `docs/PRODUCTION_HANDOFF.md` converts those blockers into a provider-neutral owner input, secret, infrastructure, recovery, monitoring, rights/policy, and production-evidence contract without inventing vendors or credentials.
- Added an image-bundled, read-only production preflight for fail-closed settings validation, exact migration-head verification, PostgreSQL/Redis reachability, private/versioned object-storage policy, and SMTP TLS/authentication. It emits stable secret-free result codes and cannot approve missing provider-policy evidence.
- Completed Phase 29 with correlated JSON request/worker logs, PII-disabled external error tracking, protected route-normalized Prometheus metrics, independent fail-closed readiness, live Studio Operations, nine alert rules, and seven incident runbooks.
- Phase 29 acceptance: 42 Chromium desktop/mobile journeys, 32 API tests, Ruff, ESLint, TypeScript, Vitest, production build, zero-vulnerability audit, alert-YAML parsing, JSON-log verification, and live authenticated metrics/readiness pass.
- Phase 29 in progress: structured JSON API/media-worker/scene-worker logs, request correlation, PII-disabled Sentry integration, protected Prometheus metrics, independent timeout-bounded readiness, live Studio Operations, alert thresholds/rules, and all seven required incident runbooks are implemented.
- Completed Phase 28 with measured frontend loading/bundle/hydration budgets, bounded public and administrator query counts, an optimized homepage request graph, local queue throughput evidence, durable streaming QoE capture, and administrator-visible startup/buffering/error/rendition metrics.
- Phase 28 acceptance: 42 Chromium desktop/mobile journeys, 30 API tests, Ruff, ESLint, TypeScript, Vitest, production build, zero-vulnerability audit, reversible QoE migration with zero drift, and live PostgreSQL/Redis/object-storage readiness pass.
- Phase 28 baseline: shipped JavaScript is 1.49 MB uncompressed across production chunks; live development homepage records approximately 160 ms TTFB, 752 ms DOMContentLoaded, 18 resources, and 787 KB transferred JavaScript. Warm API reads measure approximately 8–12 ms for the movie catalog and 4–5 ms for the homepage; full dependency readiness measures approximately 130 ms locally.
- Removed redundant movie/series hierarchy reads from the normal customer homepage render; those payloads now load only for the unpublished-homepage fallback.
- Added stable query ceilings for `/catalog/movies` (8 statements), `/catalog/series` (8), and `/homepage` (6), including the four due-schedule synchronization writes, plus desktop/mobile loading and hydration budgets.
- Completed Phase 27 security hardening: production docs are disabled; API/web security headers and production HSTS are installed; CORS is narrowed; unsafe production mutations require a trusted origin; trusted server actions forward the configured web origin; placeholder production credentials and insecure origins fail startup; CSP permits only the configured API and signed-upload object-storage origins.
- Audited administrator route protection and offline-only provisioning, session hashing/revocation/cookies, upload size/checksum/signature verification, private entitled media delivery, development-only credentials/reset disclosure, secrets, dependencies, and debug exposure.
- Phase 27 acceptance: 40 Chromium desktop/mobile journeys, 28 API tests, Ruff, ESLint, TypeScript, Vitest, production build, and zero-vulnerability dependency audit pass.
- Began Phase 27 with dependency, authorization, administrator-route, upload-validation, signed-media, session, CSRF/CORS, secret, and production-header auditing.
- Completed Phase 26 with a keyboard-visible skip path, global focus treatment, reduced-motion support, RTL-safe logical layout, semantic active-profile document language/direction, and locale/timezone-aware account formatting.
- Added validated profile language, IANA timezone, audio, primary/secondary subtitle, subtitle-default, caption size/background/position preferences and responsive account controls.
- Playback now applies saved audio/caption preferences, matches two/three-letter language aliases, retains a normal browser-native primary subtitle path, and permits one distinct second licensed subtitle without replacing or disabling the first.
- SceneLens and After-Credits Room now enter focus predictably, contain tab navigation, close with Escape, and restore focus.
- Phase 26 acceptance: 40 Chromium desktop/mobile journeys, 25 API tests, automated WCAG A/AA checks across public/account/Studio surfaces, Ruff, ESLint, TypeScript, Vitest, production build, zero-vulnerability audit, reversible migrations and zero drift, live dependency readiness, and desktop/mobile visual review all pass.
- Completed Phase 25 with lifecycle-aware private clubs, owner/moderator/member management, scheduled films, polls, spoiler discussion, shared lists, and completed member history.
- Added private synchronized rooms with hashed credentials, host-only optimistic controls, participant presence, chat/reactions, drift correction, and explicit end/leave lifecycle.
- Every party operation rechecks the participant through normal playback-source, title-rights, region, session, profile, and club-membership authorization; room access never confers content entitlement.
- Phase 25 acceptance: 36 Chromium desktop/mobile journeys, 25 API tests, Ruff, ESLint, TypeScript, Vitest, production build, zero-vulnerability audit, reversible migration and zero drift, live dependency readiness, and desktop/mobile visual review all pass.
- Completed Phase 24 behind a fail-closed publication boundary: user-generated text and lists reach other profiles only after an explicit administrator approval.
- Added normalized ratings, spoiler-aware reviews, follows, blocks/mutes, abuse reports, moderation actions, and typed activity persistence with ownership, cascade, uniqueness, range, target-shape, and self-relation constraints.
- Reused profile-owned user-list collections for community lists, adding visibility and moderation state instead of introducing a parallel list aggregate.
- Added active-profile rating and spoiler-aware review writes. Reviews are unique per profile/movie, all creates and edits enter pending moderation, and only approved records appear in customer reads.
- Added approved public-list discovery and safety-filtered following activity; stale activity never resurrects rejected, removed, private, or newly pending targets.
- Added report, follow/unfollow, mute/unmute, and block/unblock APIs. Blocking removes existing follows in both directions and prevents new follows across the boundary.
- Added Redis-backed per-profile rate limits for every community mutation family and explicit duplicate-report conflicts.
- Added a responsive movie community panel, moderated public-list controls and directory, safety-filtered activity destination, and Studio review/list/report queue with required decision reasons.
- Every moderation decision produces an administrator audit record and durable moderation action. Account deletion removes profile content while retaining a non-identifying decision tombstone.
- Phase 24 acceptance: 34 Chromium desktop/mobile journeys, 24 API tests, Ruff, ESLint, TypeScript, Vitest, production build, zero-vulnerability audit, reversible migration and zero drift, live dependency readiness, and desktop/mobile visual review all pass.
- Added an explicit curated/no-algorithm homepage mode to the shared profile preference aggregate through reversible migration `20260815_0021`.
- Added an active-profile homepage contract and validated mode mutation that changes the returned strategy immediately while preserving independent choices across profile switches and sessions.
- Added deterministic, rights-filtered browsing for recently added titles, A–Z, release year, director, country, genre, and published collection. Stable UUIDv5 rail identity and explicit tie-breaking prevent incidental ordering churn.
- No-Algorithm Mode reads no viewing history, popularity, recommendation score, inferred taste, or random signal and identifies its strategy as `deterministic_catalog_indexes_v1` in the API and UI.
- Added a responsive customer strategy panel with plain-language disclosure, immediate switching, and reload persistence.
- Phase 23 acceptance: 32 Chromium desktop/mobile journeys, 22 API tests, Ruff, ESLint, TypeScript, Vitest, production build, zero-vulnerability audit, reversible migration and zero drift, live dependency readiness, and visual review all pass.
- Phase 22 shared-domain audit maps existing SceneBookmark/SceneNote, Artwork, MusicCue, ProductionNote, Credit/Person/Company, Edition, PlaybackSource, and ViewingActivity records to the toolkit instead of duplicating feature-specific tables.
- Extended shared Artwork records with an approved scene, nonnegative spoiler timestamp, documented rights basis, and explicit gallery permission. Database and request validation require all four for permitted stills, and scene deletion cascades the dependent still so permission context cannot become orphaned.
- Added an authenticated, playable-source Cinephile contract that applies the published protected spoiler cutoff to permitted stills, music cues, and filmmaking notes while returning global non-spoiler normalized credits, existing editions, and active-profile rewatch facts.
- Added private still delivery through the API with title/source/profile authorization, current-cutoff membership checks, object-storage isolation, media typing, no-sniff protection, and private short caching; storage keys and rights-basis text are not exposed to customers.
- Added the first SceneLens Cinephile Toolkit UI: responsive permitted still gallery, timestamped music timeline without lyrics, verified filmmaking explorer, semantic credits explorer, honest edition-vault empty state, and profile rewatch summary.
- Live acceptance publishes a generated worker thumbnail as an original rights-cleared still and proves it is absent at 0:03.99 and visible at 0:04, while a sourced score cue and camera note appear at their 0:05 and 0:06 boundaries. Desktop/mobile behavior and a focused visual capture pass.
- Expanded the shared Edition domain with per-cut rights windows, intended-presentation identity, verified aspect ratio/frame rate/presentation/capture/audio/original-language/restoration/source metadata, and explicit sourced differences across inserted/removed scenes, presentation, restoration, audio, and editorial categories.
- PlaybackSource now optionally belongs to one Edition, allowing multiple separately processed media sources for a movie/episode while retaining one legacy source for existing titles. Assignment rejects cross-title editions; default available editions are selected deterministically and original-language audio is preferred when the manifest supplies it.
- Edition comparisons require two editions of the same title and carry source notes, verification state, and optional reveal positions. Cinephile responses suppress all comparison descriptions until the active profile has completed any edition of that title, then expose only manually verified records.
- Edition Vault now reports per-edition media availability, actual processed audio/subtitle tracks, runtime, restoration/source notes, and original-presentation metadata. Browser acceptance renders the intended 2.39:1/24 fps presentation and the locked comparison state; API acceptance proves two independently assigned edition sources plus post-completion comparison unlock.
- Added a film knowledge graph derived exclusively from currently visible normalized catalog data: movie roots connect to genres, themes, franchise, country, original language, credited people/roles, companies, portrayed characters, franchise titles, and other available titles sharing verified credits. It labels the derivation strategy and never invents influence/source-material links.
- Added responsive, keyboard-navigable knowledge-node cards plus an accessible edge list directly on movie detail pages, turning graph records into working search, movie, person, and company discovery links rather than storage-only metadata.
- Added first-class person/company Credits Explorer destinations that filter film, series, and episode credits through current publication/rights visibility and preserve role/character context. API acceptance proves the actor-to-character-to-film route; desktop/mobile browser acceptance follows a generated director node into the exact available title.
- Phase 21 adds an authenticated relationship-graph query over the same published, active-profile, playable-source, protected timestamp context used by SceneLens.
- Graph construction performs a second effective-cutoff check, requires both endpoints to be currently allowed entities, merges recurring entities by canonical key, omits orphan nodes, and sorts nodes/edges deterministically. The response exposes the inclusive cutoff and inherited safety state.
- Current-scene character names emphasize matching character entity nodes without exposing global biography data. Dense ensemble acceptance proves all current characters are marked while a planted post-cutoff relationship is absent.
- SceneLens renders labeled SVG nodes and edges with bounded zoom, a keyboard-scrollable pan viewport, explicit current-character styling, an accessible title/description, and an expandable semantic relationship list containing endpoint names and reveal times.
- The live browser fixture now publishes real provenance-backed Beacon/Signal entities and an `emits` edge. Desktop/mobile acceptance exercises zoom and the alternate list; visual review confirms readable nodes, edge label, controls, and responsive scrolling.
- Phase 20 adds explicit Who Was That and What Did I Miss actions to SceneLens, separate from free-form Ask This Movie, with clear loading, supported, and unavailable states.
- Who Was That returns every verified current-scene character available at the protected timestamp, actor metadata, approved prior appearance times, a bounded appearance summary, and only relationships whose endpoints and relationship reveal are already allowed.
- What Did I Miss accepts a past interval ending no later than the current playback timestamp, caps requests at 15 minutes, and joins only approved scene summaries whose completion reveal falls inside that interval. Partial or unfinished scenes remain unavailable.
- Added defense-in-depth cutoff filtering in both moment helpers, typed authenticated playable-source endpoints, dense four-character mystery/ensemble coverage containing deliberately future relationships/scenes, and exact supported/unavailable integration boundaries.
- Added desktop/mobile browser acceptance and visual review proving both controls refuse to invent an identity or recap before verified evidence is available. Repeated search acceptance now checks presence rather than nondeterministic global-result ordering.
- Phase 19 adds Ask This Movie inside SceneLens as a retrieval-grounded question workflow using the named deterministic `structured_templates_v1` strategy rather than claiming an unconfigured generative model.
- Every request identifies the authenticated active profile, playable movie/episode source, current timestamp, spoiler mode, currently published intelligence version, and Phase 17 allowed fact range before intent routing.
- Added bounded intent handling for current character/actor, completed-scene recap, approved relationships, music cues, production notes, and named entities. Answers are assembled only from returned structured fields and never from raw future cues or unrestricted catalog biography text.
- Unsupported questions, incomplete scene boundaries, missing actor/craft data, and absent evidence return one explicit reliable-information-unavailable answer with `unavailable` confidence and a concrete uncertainty reason.
- Added profile-weighted Redis request limiting and typed responses exposing strategy, intent, confidence, uncertainty, non-sensitive evidence kind/timestamp labels, and inherited safety state.
- Added AskMovieLog records containing a SHA-256 question digest—not raw question text—plus profile/source/version/timestamp/mode, intent, outcome, and exact internal fact ID/kind/reveal provenance.
- Added migration `20260815_0015`, API acceptance for supported character/actor answers, blocked pre-ending recap, available boundary recap, unsupported refusal, and provenance timestamp integrity, plus desktop/mobile in-player refusal acceptance and visual review.
- Phase 18 adds SceneLens directly to the adaptive player as a narrow desktop side panel and bounded mobile bottom sheet, leaving the video visible and playback controls available.
- SceneLens activates through an explicit Lens control, `L` keyboard shortcut, and a non-obscuring “SceneLens ready” affordance whenever playback pauses.
- The overlay consumes only the Phase 17 spoiler-safe context contract and renders the current scene, reveal-safe summary state, verified characters and actors, prior approved appearances, relationship labels, music cues, and sourced production/detail notes.
- Character/actor resolution uses normalized Character/Credit/Person records for the current movie/episode; missing actor data remains explicitly unavailable. Character summaries report only prior timestamp-approved appearances rather than global biography text.
- Added profile-private SceneBookmark and SceneNote persistence with source/scene/timestamp ownership, bounded title/body fields, duration and scene-containment validation, cascade deletion, and owner-only deletion.
- Added bookmark and note creation/deletion inside SceneLens with timestamp labels and explicit private-to-profile copy. No frames or protected media bytes are captured or redistributed.
- Added migration `20260815_0014`, API acceptance for current scene, character/actor resolution, bookmark/note persistence and deletion, and real desktop/mobile browser acceptance through paused playback and spoiler-hidden summary state.
- Stabilized CPU-intensive live-media acceptance at two parallel Playwright workers with 15-second assertion tolerance; this preserves parallel desktop/mobile coverage without saturating the local FFmpeg/Next/PostgreSQL stack.
- Phase 17 adds one authenticated, active-profile spoiler retrieval boundary over the currently published scene-intelligence version for an assigned, publicly playable source.
- Protected mode applies an explicit inclusive policy: a fact is available only when its validated reveal timestamp is `<= T`. Scene summaries and transcript cues use their end timestamps so entering a scene cannot expose its outcome.
- Relationship visibility is the maximum of the relationship, subject, and object reveal timestamps; later relationships and entities therefore remain suppressed even when their containing scene is otherwise known.
- Full-spoiler mode is denied until the active profile has a persisted completed ViewingActivity for that exact playback source. Completion and subsequent rewatch cycles keep the deliberate full-context unlock available.
- Every returned fact must belong to the published version's provenance set, valid scene, playback duration, and finite numeric domain. Cross-version, non-finite, structurally inconsistent, or otherwise malformed evidence is counted and omitted with a fail-closed safety state.
- Added typed responses with requested/effective cutoff, equality policy, completion unlock, returned facts, per-kind withheld counts, and explicit no-published-evidence/malformed-evidence states.
- Acceptance proves a fact before T, equality at T, a later fact, a later relationship, an ending scene, locked/unlocked full mode, rewatch behavior, non-finite metadata, and out-of-range request handling.
- Phase 16 adds a dedicated Redis-backed scene enrichment worker that ingests only extracted subtitle/transcript tracks explicitly matched to administrator-declared provenance and license basis.
- Added bounded WebVTT parsing with UTF-8 decoding, tag normalization, both standard timestamp forms, ordered/range validation, a 5 MiB ceiling, and safe failed-job states for missing or malformed evidence.
- Added deterministic timestamp alignment to existing scenes and conservative gap/maximum-duration segmentation when no scenes exist. Generated scenes retain subtitle provenance, extractive summaries, 0.65 confidence, and an unverified state; no character or filmmaking metadata is guessed.
- Added durable TranscriptCue records plus generated PostgreSQL `tsvector` SceneSearchDocument records and a GIN index; administrator search ranks matching scene titles, summaries, and aligned dialogue.
- Added operational enrichment queue progress/error/attempt visibility, extracted-evidence URI discovery, lawful-basis guidance, and indexed scene search in Studio.
- Added real development acceptance using an original generated MP4 with embedded captions: upload → extract WebVTT → declare provenance → enrich → align → index → search → validate → publish.
- Corrected analytics day aggregation to derive calendar dates explicitly in UTC, fixing the real local-midnight/UTC-midnight boundary uncovered by repeated acceptance runs.
- Phase 15 adds versioned, playback-source-owned scene intelligence with explicit draft, review, validated, and published lifecycle states; validated and published evidence is immutable.
- Added provenance-bearing Scene, Chapter, SceneCharacter, SceneEntity, SceneRelationship, MusicCue, ProductionNote, SpoilerBoundary, SceneSource, SceneIntelligenceVersion, and enrichment-job records with relational integrity, time/confidence constraints, and cascade-safe ownership.
- Added protected, audited administrator APIs for version creation, evidence sources, scene CRUD/correction, structured records, enrichment queueing, structural validation, and atomic publication that demotes the prior published version.
- Validation rejects absent evidence, discontinuous ordinals, foreign provenance, out-of-duration facts, and overlapping scenes/chapters; malformed request metadata is bounded by typed contracts and database constraints.
- Added a responsive Scene Data Studio workflow for source selection, immutable evidence versions, provenance/license capture, manual scene entry and correction, enrichment queueing, validation errors, and publication. It explicitly exposes no chatbot or customer answer surface.
- Added API acceptance across every Phase 15 record family and browser acceptance that creates, validates, publishes, and visually verifies a manually sourced scene version against real generated playback.
- Phase 14 adds a durable, profile-owned ViewingActivity ledger independent of the bounded raw analytics retention window, with numbered title cycles, explicit first-watch/rewatch identity, observed playback seconds, lifecycle timestamps, and completion state.
- Playback creates one activity on first progress, updates bounded client-reported watch seconds, completes it on the 90% boundary, ignores repeated completion saves, and opens a rewatch only after a completed title restarts below 20%.
- Migration `20260815_0011` backfills existing progress as first activities and provides profile/time and completion indexes, integrity constraints, cascade ownership, and a verified downgrade/re-upgrade path.
- Added authenticated active-profile lifetime and yearly Passport reports with films/episodes watched, completed views, first watches, rewatches, observed hours, favorite genres/creators, country/decade distributions, longest/shortest completed titles, milestones, and a bounded history ledger.
- Creator rankings join real normalized catalog credits and weight only completed viewing activities. Annual report years derive from persisted activity timestamps rather than generated placeholders.
- Added explicit private-to-profile response state and UI disclosure; reports are not publicly shareable until deliberate privacy controls exist.
- Added a responsive Cinema Passport destination with lifetime/year navigation, statistic cards, distributions, creator rankings, empty metadata states, and first-watch/rewatch history.
- Extended API acceptance through a real first completion followed by a replay cycle, proving exactly one first watch, one rewatch, creator weighting, yearly selection, privacy, and durable history.
- Extended the generated-video browser loop to complete the uploaded title and observe the exact title plus First watch · Completed in Cinema Passport at desktop/mobile sizes.
- Fixed a mobile Studio homepage pin-control hit-target overlap found during full regression by isolating the inline form, stacking its action safely, and verifying keyboard activation.
- Phase 13 adds a transparent Taste DNA projection derived only from the active profile's persisted movie/episode watch progress; empty profiles return an explicit zero-evidence cold-start state.
- Added completion-weighted genre, theme, tag, decade, country, and language affinities plus observed runtime average, completion rate, confidence tiers, and plain-language insights backed by returned dimensions.
- Added a bounded `prescription_rules_v1` movie matcher accepting time, mood, pacing, intensity, preferred/unwanted genres, unwanted characteristics, language, release era, and watched/unwatched intent.
- Hard constraints filter eligibility through the same publication/rights boundary as the public catalog. Mood, pacing, and intensity match only controlled theme/tag evidence; missing metadata is labeled unavailable rather than inferred.
- Added one-best-fit output with deterministic score/order, concise evidence-derived reason, constraint satisfaction, per-dimension matched/neutral/unavailable states, View & Play, and a working exclusion-backed Another Recommendation action.
- Added a responsive Movie Prescription and Taste DNA experience, API validation for coherent/known constraints, and profile isolation through the active authenticated session.
- Extended API acceptance with two profiles seeded with different persisted viewing histories, proving distinct Taste DNA genre affinities and meaningfully different prescribed movies.
- Extended desktop/mobile browser acceptance through cold-start Taste DNA, a bounded runtime prescription, reason/dimension rendering, and visual inspection.
- Phase 12 adds a deterministic `rules_v1` recommender across published, currently available movies and series; the product and API explicitly identify it as rules-based rather than machine learning.
- Added weighted editorial, watched-title taxonomy similarity, explicit profile genre preference, 30-day aggregate popularity, and cold-start signals with stable tie-breaking and per-result reason codes.
- Added profile-scoped watched exclusion for any movie or series with watch progress, including episode-to-series resolution, and reports the exclusion count without leaking another profile's history.
- Added an authenticated preference API that normalizes, de-duplicates, bounds, and validates genre slugs before storing them in the existing profile preference boundary.
- Added a responsive authenticated Discover destination with movie/series cards, human-readable reasons, cold-start messaging, watched-exclusion disclosure, and an explicit explainability statement.
- Added API acceptance for authentication, cold start, preference influence, duplicate normalization, popularity, similarity, and watched exclusion plus desktop/mobile browser acceptance and visual review.
- Phase 11 adds typed raw AnalyticsEvent records for impressions, detail opens, playback lifecycle, search/search-click, My List, rating, SceneLens, and Ask This Movie signals plus separate daily AggregatedMetric records.
- Added authenticated profile/session attribution, client UUID idempotency, 30-second progress coalescing, Redis event-weighted rate limiting, 25-event batches, strict timestamp windows, a 4 KiB/20-key property ceiling, and a property allowlist that rejects unsupported PII-like fields.
- Added configurable 90-day raw retention with bounded 500-row cleanup work while anonymous daily aggregates remain available for longer-term reporting.
- Added bot/internal flags and aggregate exclusion rules, platform totals, unique viewers, watch hours, completion rate, per-title plays/completions/watch time, and restricted recent raw-event inspection.
- Instrumented the adaptive player for play-start, progress, pause, seek, and completion and signed-in search for query/result-count events without disrupting anonymous browsing.
- Added an operational responsive Studio Analytics destination with KPI cards, daily aggregate bars, per-title performance, raw/aggregate distinction, retention disclosure, and recent restricted events.
- Extended playback acceptance to verify exact profile/title events in PostgreSQL and then observe the resulting title and event types in Studio Analytics at desktop/mobile sizes.
- Phase 10 adds persistent Plan, Subscription, PaymentReference, and Entitlement boundaries with explicit lifecycle enums, period/window constraints, provider references, and seeded active plan catalog records.
- Added a billing-provider protocol and environment configuration boundary. The development stub is labeled non-production, is rejected in staging/production configuration, returns 503 for checkout, and never creates or simulates a completed payment.
- Added an authenticated account dashboard API exposing the viewer's current subscription, active entitlements, active owned device sessions, plans, and truthful billing capability state.
- Added customer-owned individual session revocation, sign-out-other-sessions, and password rotation that preserves the current session while revoking every other active session.
- Added a responsive customer Account & Access dashboard for subscription state, profiles, plan catalog, device/session inspection and revocation, and password change.
- Added API and desktop/mobile browser acceptance proving two simultaneous devices, other-session revocation, revoked-cookie rejection, password rotation, new-credential login, and absence of fake billing.
- Phase 9 adds a real Studio Homepage destination with curated hero selection, named/query-backed rails, manual pins, rail/item ordering, enable/disable controls, UTC visibility windows, private draft preview, and atomic live publication.
- Added relational HomepageConfiguration, HomepageRail, and HomepageItem draft records plus an immutable published JSON snapshot so partially edited layouts never leak to customers.
- Added customer homepage resolution for pinned, latest-movie, latest-series, and mixed sources with deterministic de-duplication, query filtering, published-title enforcement, rights-window enforcement, and scheduled rail visibility.
- Added movie/series publish-later, unpublish-later, rights-start, and rights-end instants with timezone-required API validation, PostgreSQL window constraints, UTC storage, automatic due-state transitions, and Studio scheduling controls.
- Added browser acceptance proving a movie can be created, published, chosen as hero, pinned, rails reordered, privately previewed, atomically published, and observed on the customer homepage without source edits.
- Pinned jsdom 26.1.0 and deduplicated the test dependency graph to keep the DOM unit suite compatible with the current local Node runtime; dependency audit remains clean.
- Phase 8 links exactly one Ready processing output to a movie or episode through an explicit PlaybackSource, including optional intro, recap, and credits markers.
- Added authenticated, profile-aware playback configuration plus same-origin credentialed delivery of HLS manifests, playlists, subtitles, and byte-range segments without exposing object-store credentials or internal keys.
- Added a custom HLS.js player with native fallback, play/pause, seek, volume, mute, fullscreen, picture-in-picture, speed, Auto/manual quality, audio/subtitle selection, retry, buffering/error states, keyboard shortcuts, Media Session metadata, skip markers, and next-episode navigation.
- Added profile-scoped watch progress with validated/clamped duration and position, completion percentage, ten-second throttled saves, pause/page-exit persistence, and leave/return resume.
- Added Studio playback assignment controls and customer Play availability driven by real processing state rather than placeholders.
- Added desktop/mobile browser acceptance using generated 720p source media, three adaptive renditions, manual/Auto quality selection, seeking, persistence inspection, and resume verification.
- Phase 7 adds a persistent Redis-backed processing queue and independently running Python media worker with idempotent queued-job claims, explicit lifecycle/progress, attempts, errors, and retry.
- Added FFprobe source inspection and validation for supported video and text-subtitle codecs, dimensions, duration, format, bitrate, audio/subtitle tracks, and chapters.
- Added source-aware H.264/AAC renditions, HLS variant playlists and adaptive master packaging, WebVTT subtitle extraction when supplied, thumbnails, and preview sprite sheets.
- Added validation of playlist termination, referenced segments, master structure, and actual FFprobe playback discovery before a job can become Ready.
- Added stable processed-object prefixes, server-only temporary directories/credentials, object-storage cleanup before retries, and persisted output keys without exposing local paths.
- Added an operational auto-refreshing Studio Processing dashboard with queue stage, percentage, source metadata, rendition status, errors, retry controls, and Ready output summaries.
- Installed FFmpeg 9.0.1 and added integration plus desktop/mobile acceptance coverage using generated original development video fixtures.
- Phase 6 adds authenticated direct browser-to-MinIO video uploads through short-lived, method-constrained signed URLs; raw object-storage credentials never reach the browser.
- Added persistent MediaAsset records with stable UUID-derived object keys, original filename metadata, media type, byte size, SHA-256, lifecycle state, ETag, failure detail, and timestamps.
- Added MP4, WebM, and QuickTime allowlisting, a configurable 5 GiB ceiling, path-safe filename validation, container-signature checks, stored-length checks, metadata checks, and server-streamed SHA-256 verification.
- Added upload initialization, live hashing/transfer progress, completion verification, explicit failure, cancellation, and retry state transitions with administrator audit events.
- Added an operational responsive Studio Uploads page with chunked browser hashing, direct XMLHttpRequest transfer, progress, cancel affordance, error reporting, and recent asset registry.
- Added restricted acceptance helpers that verify the browser-created database record and MinIO object without exposing storage credentials.
- Phase 5 turns Studio into an operational CMS with Dashboard, Content, Movies, Series, and Settings destinations; future operational areas are visibly labeled `Later` rather than presented as dead links.
- Added a searchable content library with type/status filters plus edit, private-preview, publish, and unpublish controls.
- Added browser movie draft creation and metadata/artwork editing backed by authenticated server actions and the existing audited administrator API.
- Added browser series draft creation plus ordered season, individual episode, and bulk episode-row workflows.
- Added private Studio previews that render draft movie and series catalog data without weakening the published-only customer boundary.
- Added publish/unpublish controls and clear persistence notices, lifecycle badges, empty states, responsive layouts, and Studio security-state settings.
- Added restricted E2E database inspection/cleanup tooling for development-test fixtures and acceptance tests that prove browser-created drafts reach PostgreSQL.
- Phase 4 renders the customer home hero, movie/series rails, reusable content cards, movie library, series library, and backend-driven catalog states.
- Added dynamic movie details with full available metadata, credits, related-title state, honest playback availability, and explicit future My List state.
- Added dynamic series details with a working season selector, ordered episodes, runtime/progress labels, and honest playback availability.
- Added search across published movie/series titles plus people, genres, and tags, including prompt and no-result states.
- Added meaningful streamed loading skeletons, inline empty states, recoverable error UI, and a catalog-specific 404.
- Added responsive/touch layouts, keyboard focus treatment, reduced-motion handling, semantic landmarks, labels, and disabled-state explanations.
- Phase 2 authentication and profiles is accepted and remains passing.
- Added ORM domain definitions for Movie, Series, Season, Episode, Edition, Person, Character, Credit, Company, Franchise, Genre, Theme, Tag, Language, Country, Artwork, and Trailer/Clip metadata.
- Added catalog lifecycle, artwork-kind, and preview-kind enums; normalized taxonomy joins; ownership foreign keys; uniqueness/check constraints; and query indexes in metadata.
- Added and applied the catalog Alembic migration, including a verified downgrade/re-upgrade path and enum cleanup.
- Added typed create/update/response contracts and transactional catalog services with reference validation and conflict handling.
- Added protected, audited administrator CRUD for titles, hierarchy, editions, credits, artwork, previews, taxonomies, people, companies, franchises, languages, and countries.
- Added customer read/search APIs that expose only published titles and filter unpublished episodes.
- Added an idempotent development-only seed with original demo metadata; it refuses to run outside development/test.
- Phase 1 live foundation remains running and accepted.
- Added customer registration, login, logout, logout-all, and current-account endpoints.
- Added Argon2id password hashing and opaque database-backed session tokens stored only as hashes.
- Added customer profile create/list/edit/delete/switch APIs with language, maturity, kids, playback, subtitle, and Cinephile Mode preferences.
- Added separate Admin/AdminSession models, interactive single-admin provisioning, login/logout, server-side authorization, rate limiting, and audit events.
- Added trusted-origin enforcement and secure cookie attributes appropriate to development/production.
- Added `/studio/login`, optimistic Proxy protection, and secure render-time API authorization for `/studio`.
- Added customer registration, login, forgotten-password, reset-password, and profile-selection screens.
- Added encrypted TOTP enrollment/confirmation, login challenges, and hashed one-use recovery codes for administrators.
- Added one-use, expiring password-reset tokens, full session revocation after reset, development reset links, and SMTP delivery requirements outside development/test.
- Browser-verified customer registration, profile creation/switching, password reset, unauthorized Studio blocking, and provisioned-admin login at desktop/mobile sizes.

FILES CHANGED:
- Root workspace/package configuration and runtime ignores.
- `apps/web`: Next.js application, customer/Studio shells, styling, lint/type/test configuration.
- `apps/api`: FastAPI application, settings, database foundation, readiness checks, tests, and Alembic migration.
- Phase control documentation.

MIGRATIONS:
- `91f3a6c2d8b4` persisted malware scan status/engine/signature/time with a bounded status constraint; downgrade to `4d91c8a7f2e0`, re-upgrade, and zero-drift check PASS.
- `4d91c8a7f2e0` default-off optional analytics consent and last-change timestamp; downgrade to `d2b94a1786ef`, re-upgrade, and zero-drift check PASS.
- `7f3d28a8d301` bounded playback startup, buffering, fatal-error, and rendition-change analytics events.
- `20260815_0001` foundation.
- `20260815_0002` users, profiles/preferences, device sessions, single administrator, admin sessions, and audit logs.
- `20260815_0003` password-reset tokens and administrator MFA recovery codes.
- `638bc495ce1d` complete normalized catalog domain.
- `20260815_0005` media asset upload registry and lifecycle.
- `20260815_0006` processing jobs, metadata, rendition state, outputs, attempts, and lifecycle.
- `20260815_0007` playback-source assignments, skip markers, and profile-scoped watch progress.
- `20260815_0008` homepage draft/snapshot curation and movie/series scheduling/rights windows.
- `20260815_0009` plans, subscriptions, external payment references, and entitlement windows.
- `20260815_0010` bounded raw analytics events and daily aggregate dimensions.
- `20260815_0011` durable numbered profile viewing activities for lifetime history and rewatches.
- `20260815_0012` versioned scene intelligence, provenance, structured facts, spoiler boundaries, and enrichment jobs.
- `20260815_0013` aligned transcript cues and generated PostgreSQL full-text scene search documents with a GIN index.
- `20260815_0014` profile-private scene bookmarks and timestamped notes.
- `20260815_0015` privacy-minimized Ask This Movie provenance logs.
- `20260815_0016` rights- and timestamp-constrained Cinephile still-gallery metadata.
- `20260815_0017` edition presentation/rights metadata, verified differences, and edition-owned playback sources.
- The development and isolated staging databases report `b7e4c91d2a60 (head)` after a successful downgrade to `91f3a6c2d8b4` and clean re-upgrade. The current staging backup restored at this head with all 91 public tables present.
- Playback-QoE downgrade to `59d824385095` and clean re-upgrade -> PASS.
- Edition-vault downgrade to `20260815_0016` and clean re-upgrade -> PASS. Downgrade intentionally removes edition-specific sources before restoring the legacy one-source-per-title constraint.
- Permitted-gallery downgrade to `20260815_0015` and clean re-upgrade -> PASS.
- Ask provenance-log downgrade to `20260815_0014` and clean re-upgrade -> PASS.
- SceneLens bookmark/note downgrade to `20260815_0013` and clean re-upgrade -> PASS.
- Scene-ingestion/index downgrade to `20260815_0012` and clean re-upgrade -> PASS.
- Scene-intelligence downgrade to `20260815_0011` and clean re-upgrade -> PASS.
- Viewing-activity downgrade to `20260815_0010` and clean re-upgrade -> PASS.
- Analytics downgrade to `20260815_0009` and clean re-upgrade -> PASS.
- Subscription/entitlement downgrade to `20260815_0008` and clean re-upgrade -> PASS.
- Homepage/scheduling downgrade to `20260815_0007` and clean re-upgrade -> PASS.
- Playback/progress downgrade to `20260815_0006` and clean re-upgrade -> PASS.
- Processing-job downgrade to `20260815_0005` and clean re-upgrade -> PASS.
- Media-asset downgrade to `638bc495ce1d` and clean re-upgrade -> PASS.
- Catalog downgrade to `20260815_0003`, clean re-upgrade, and reseed -> PASS.

TESTS:
- Current production-readiness increment: API lint PASS; API tests PASS 84/84; current-schema enabled-feature staging Chromium PASS 46/46; separate all-risky-features-off staging PASS 4/4; protected-CDN edge tests PASS 4/4; trusted geo-ingress tests PASS 2/2; web TypeScript/ESLint PASS; Vitest PASS 14/14; production build PASS; atomic simultaneous-stream lease tests PASS; malware clean/detected/outage/retry, Studio quarantine presentation, public multipart signing, and ClamAV protocol/preflight/config checks PASS; isolated restore PASS at `b7e4c91d2a60` with 91 tables; dummy Toronto rendering and dummy launch-evidence NO-GO validation PASS.
- DigitalOcean rendered-spec audit: required browser build origins are present; the template-only YAML extension is absent from output; database/Stripe/Spaces/SMTP/session/monitoring secrets are scoped to API, migration, and workers and absent from the web component; all component environment contracts and managed-database bindables passed structural assertions.
- Production image audit: both API and web Dockerfiles built successfully from the current workspace as `aperture-*:production-readiness`; both runtime images execute as the non-root `aperture` user; the API image imports Stripe 13.2.0 and contains the migration tooling; the web image contains the supplied dummy `/api` public origin in its compiled client bundle rather than a localhost fallback.
- App Platform routing audit: the rendered spec uses current ordered ingress rules with `/api` routed to FastAPI before `/` reaches Next.js, contains no deprecated component `routes`, and enables deployment/domain failure alerts.
- App Platform release-order audit: the rendered target runs Alembic as `PRE_DEPLOY`, the complete dependency/Stripe preflight as `POST_DEPLOY`, and bounded catalog/retention work as a five-minute `SCHEDULED` job; all three receive the same validated API runtime contract.
- Backup image/spec audit: the Hostinger backup candidate uses digest-pinned Python 3.12.14 Alpine rather than a PostgreSQL server image, runs as fixed non-root UID/GID 10001 under the read-only Compose contract, and adds the pinned PostgreSQL 17.11 client plus boto3 1.42.54. Backup and restore imports, `pg_dump`/`psql` 17.11 runtime checks, and a Docker Scout 0-critical/0-high scan pass locally. Real provider execution, retention, isolated restore, and measured RPO/RTO are still unproven.
- Current-schema staging restore audit: a new backup restored into a separately named database at `b7e4c91d2a60` with 91/91 public tables, then the validated temporary database and files were removed. The production-format verifier separately covers private object download, manifest binding, size/SHA-256, empty-target enforcement and parity. This does not replace DigitalOcean evidence.
- App Platform rollback readiness audit: dummy mode made no provider call; read-only inspection requires the exact successful deployment; execution requires an explicit confirmation and posts only that deployment ID; all error output is credential-redacted. No live rollback or traffic-health claim is made.
- Public-edge smoke audit: six non-mutating checks passed against isolated staging HTTPS, covering customer HTML, API dependency readiness, required browser/API security headers, request-ID propagation, and anonymous denial for account, Studio support, and metrics. Production mode additionally requires HSTS and hidden docs/OpenAPI; real public DNS/TLS has not been tested.
- Credential handoff increment: dummy configuration rendered without network calls; DigitalOcean bindables were preserved; rendered YAML parsed successfully; input/output permissions verified as mode 0600; deploy mode correctly rejected all dummy inputs; renderer lint passed.
- Current production-target increment: API lint PASS; API tests PASS 41/41; billing-webhook migration downgrade/re-upgrade and Alembic drift PASS; DigitalOcean app-template YAML sanity PASS; web TypeScript, ESLint, Vitest, and production build PASS.
- `npm run typecheck:web` -> PASS.
- `npm run lint:web` -> PASS.
- `npm run test:web` -> PASS, 1 test.
- `npm run build:web` -> PASS; static and dynamic routes compiled for production.
- `npm run test:e2e` -> PASS, 42 Chromium tests across desktop/mobile, including measured loading/hydration budgets, generated playback QoE, fail-closed moderation, accessibility/i18n, clubs/parties, and all prior regressions.
- `npm audit --audit-level=high` -> PASS, 0 vulnerabilities after upgrading Playwright to 1.62.1.
- `ruff check .` -> PASS.
- `pytest` -> PASS, 30 tests covering prior domains plus production security configuration, origin enforcement, bounded catalog/analytics query counts, playback QoE validation/reporting, and all prior safety contracts; one upstream Starlette TestClient deprecation warning.
- `GET /ready` -> PASS for PostgreSQL, Redis, and object storage.

LIVE VERIFICATION:
- Current 2026-08-18 check: hot-reload customer UI returns HTTP 200; API dependencies report database, Redis, and object storage `ok`; Colima/Docker and the isolated HTTPS staging stack are running; staging customer edge returns HTTP 200 and staging API readiness reports all dependencies healthy.
- Hot-reload customer URL: <http://localhost:3000> — running and returning server-rendered HTML.
- Hot-reload Admin URL: <http://localhost:3000/studio> — running with its authentication boundary.
- Hot-reload API URL: <http://localhost:8000> — running; `/ready` reports database, Redis, and object storage `ok`.
- Development API docs: <http://localhost:8000/docs> — running.
- Development MinIO console: <http://localhost:9001> — running on loopback.
- Customer URL: <https://staging.127.0.0.1.nip.io:8443> — running through the isolated Caddy HTTPS edge.
- Admin URL: <https://staging.127.0.0.1.nip.io:8443/studio> — running with server-side administrator protection.
- API URL: <https://api.staging.127.0.0.1.nip.io:8443> — running; health and full dependency readiness pass.
- Object delivery URL: <https://storage.staging.127.0.0.1.nip.io:8443> — running behind the private staging storage boundary.
- Mailpit console: <http://127.0.0.1:58025> — running for isolated SMTP acceptance.
- Browser result: PASS, 46 enabled-feature Chromium tests across Desktop Chrome and Pixel 7; four all-flags-off-only cases were intentionally skipped in this enabled build. Performance budgets, privacy consent, generated-media processing/playback, community, clubs, accessibility/i18n, SceneLens, Studio operations, and all prior enabled regressions remained green.
- Public-edge smoke: PASS, six credential-free checks covering HTTPS HTML, security headers, request-ID propagation, dependency readiness, and protected API denial.
- Restore result: PASS at migration `b7e4c91d2a60`, with all 91 source tables present in a separately named restored database before safe cleanup.
- Console errors: none.
- Network errors: none.
- Live catalog verification: published seeded movie and series return from PostgreSQL through customer APIs; readiness remains healthy.

KNOWN ISSUES:
- Territory enforcement is locally complete across catalog, community/club, playback, media, and CDN boundaries. Production still requires deployment of the trusted geo ingress, direct-origin binding, and public multi-country allowed/denied evidence; raw client country headers remain untrusted by design.
- Feature-off navigation, control visibility, direct-route status, backend router absence, screenshots, console errors, failed requests, and 5xx responses are now covered by a repeatable real-HTTPS staging rebuild. The all-off desktop/mobile Chromium gate passes 4/4 and automatically restores the enabled stack; the restored normal matrix passes 46/46.
- The account privacy UI and full consent lifecycle now pass deployed desktop/mobile acceptance: default-off state, pre-consent 403, explicit grant and 202 ingestion, persisted raw-event evidence, withdrawal erasure, post-withdrawal 403, No Algorithm persistence, screenshot, console, and request-failure checks.
- The current deterministic radial layout is appropriate for the bounded development graph and supports zoom/scroll. Production-scale dense graphs will need collision-aware layout, clustering, focus navigation, and performance budgets while retaining the semantic alternate list.
- What Did I Miss currently uses a fixed last-30-seconds SceneLens action; the API supports any validated past interval up to 15 minutes, but custom accessible interval selection is deferred until user research establishes the right player interaction.
- Ask This Movie is intentionally a bounded structured-template engine for the approved development corpus. Broader natural-language coverage requires a separately evaluated model/provider configuration, prompt-injection tests, cost/latency controls, and the same immutable retrieval/provenance contract; the current product never implies otherwise.
- Raw questions are not retained; SHA-256 digests support coarse audit correlation without a query transcript. Production privacy review may require keyed hashing or no digest at all depending on policy and threat model.
- SceneLens uses the approved production-note categories currently present in scene intelligence; filming locations, easter eggs, VFX, editing, and cinematography remain absent when Studio has no sourced evidence. It does not fabricate empty modules.
- Bookmarks and notes are private and timestamped but do not yet expose folders/tags or a cross-title gallery; the Phase 22 My List and rewatch surfaces reuse them without claiming that broader organization UI.
- Phase 17 exposes the spoiler-safe retrieval contract but deliberately has no customer overlay yet; Phase 18 SceneLens will be its first consumer. Full mode currently unlocks from persisted completion history rather than a separate per-profile spoiler preference control.
- Phase 16 deliberately avoids embeddings because PostgreSQL full-text search satisfies the current bounded development corpus. Character links remain manual unless future evidence provides an adequate, testable confidence basis; no customer chatbot surface exists yet.
- Scene summaries are conservative extractive summaries over lawfully declared captions. Production semantic summarization requires an evaluated, provenance-preserving model pipeline before it can replace this safe baseline.
- Passport watch hours are deliberately labeled observed hours and sum bounded playback-reported deltas; they do not assume an entire runtime was watched after completion. Offline reconciliation and multi-device concurrent-cycle handling need scale testing.
- Rating persistence and customer averages now exist, but Passport intentionally does not incorporate favorite-rated films or rating-history deltas until a separately evaluated projection is added.
- Public annual-report sharing is disabled until explicit per-profile privacy controls, revocation, unguessable share tokens, and safe field selection are implemented.
- Existing pre-Phase-14 progress is backfilled as one first activity. Historical rewatches that occurred before the durable ledger existed cannot be reconstructed truthfully.
- Taste DNA currently reflects watch progress, completion, and the catalog dimensions actually modeled. Ratings, watchlist intent, replay detection, and creator/craft affinities require their owning persistence phases before they can truthfully influence it.
- Mood, pacing, and intensity coverage depends on normalized theme/tag metadata. Sparse titles remain explicitly unavailable; a future Studio metadata vocabulary and coverage report should improve—not fabricate—these dimensions.
- Movie Prescription evaluates the current small eligible catalog on demand. Production scale requires indexed/cached candidate filtering, experimentation/evaluation infrastructure, and diversity controls without weakening hard constraints.
- Recommendations are on-demand rules over the current small catalog. Production scale requires cached candidate sets, invalidation on catalog/editorial changes, series-level popularity rollups, and offline evaluation of rule weights.
- Explicit taste controls currently expose a validated API but not a dedicated customer preference editor; the Phase 13 Taste DNA and Movie Prescription experience will provide the richer customer-facing input surface.
- Watched exclusion currently hides a title after any saved progress. A future customer control may distinguish "hide watched," completed-only exclusion, replay intent, and deliberate dismissals.
- Analytics ingestion and small-scale aggregate recomputation are synchronous in the API for correctness and immediate observability. Production volume requires queue-backed ingestion, partitioning, late-event reconciliation, and an independently scheduled retention/rollup job.
- Customer analytics currently require an authenticated active profile; anonymous homepage/search behavior is deliberately excluded until consent, anonymous-ID rotation, and regional privacy policy are implemented.
- QoE collection currently has the schema keys and player lifecycle foundation but does not yet calculate robust buffering/error percentiles or retention curves.
- Stripe subscription Checkout, customer Billing Portal handoff, signed/idempotent subscription and invoice webhook reconciliation, failed-payment state, and durable payment references are implemented. Fake test credentials are accepted only outside production and automated tests make no network calls; production requires owner-injected live credentials and full Stripe test/live acceptance before billing launch.
- Webhook processing does not trust delivery order: after signature verification it performs a read-only retrieval of the current Stripe subscription/invoice, rejects ownership/provider/customer mismatches, then commits the provider-authoritative state and idempotency record together.
- Refund execution, tax calculation, trials, and coupons remain opt-in production billing-provider configuration rather than simulated features. Payment-method, cancellation, renewal, and plan-management UX is delegated to Stripe's provider-authoritative portal. Portable export and confirmed account deletion are implemented; applicable legal policy and response-process approval remain production-owner responsibilities.
- Due catalog transitions remain transactionally synchronized on public reads and are additionally materialized by the Hostinger five-minute UTC maintenance job; the same job performs bounded raw-analytics retention independently of customer traffic.
- Homepage audience/profile targeting remains intentionally deferred, as allowed by the product specification; the published snapshot is currently global.
- Development/staging media uses the authenticated API proxy. Production requires the implemented protected CDN mode: short-lived source/session HMAC paths, edge verification before cache access, secret origin revalidation, immutable output caching, and uncached range forwarding.
- The original development seed uses generated visual treatments because no licensed artwork or video asset is attached yet.
- Upload completion still verifies SHA-256 synchronously with constant memory; probe/transcode and derived-output work runs in the separate Phase 7 worker.
- Uploads above 16 MiB use durable private multipart sessions with fixed-size signed parts, authoritative resume discovery, pause/reselection resume, server-side completion, safe abort, and final streamed SHA-256/container validation. Smaller uploads retain the simpler signed single PUT.
- Collection and Film Journey persistence/discovery, Studio editing, and private customer progress are implemented. Optional achievement badges remain deliberately absent because no durable achievement domain is required by the accepted journey experience.
- The After-Credits Room is profile-completion gated and exposes only published provenance-backed editorial modules. Phase 24 ratings and moderated reviews remain on movie/community surfaces; they are not silently injected into the room.
- Explicit directed film relationships are persisted with required source notes, administrator verification, audited Studio writes, and rights-filtered graph projection; influence is never inferred from shared metadata.
- Rewatch intelligence is profile-controlled and only surfaces prior completion, saved scenes, and notes after a second viewing starts. Rating/favorite deltas remain unavailable until durable ratings/favorites exist.
- Media processing and Scene enrichment both have row-locked claims, expiring owner heartbeats, stale-owner rejection, bounded crash recovery, terminal attempt limits, and independently supervised Hostinger worker services. Provider capacity and failure drills remain launch evidence rather than repository claims.
- Device/session management and password-change UI are implemented and browser-verified in the account dashboard.
- Administrator MFA enrollment, recovery-code presentation, recovery login, and sign-out are implemented and browser-verified in Studio.
- Real SMTP delivery requires deployment credentials and will be verified in staging; non-development startup rejects missing SMTP configuration.
- Native Redis is kept alive as a direct local process due an incompatible pre-existing Homebrew Redis module configuration.
- Workspace is not initialized as a Git repository.

CURRENTLY RUNNING SERVICES:
- Next.js hot-reload development server on port 3000.
- FastAPI/Uvicorn reload development server on port 8000.
- Native PostgreSQL 17 on loopback port 5432.
- Native Redis 8 on loopback port 6379.
- Native MinIO API/console on loopback ports 9000/9001.
- Native Redis-backed development media and scene-enrichment workers.
- Immutable Next.js/FastAPI staging services, PostgreSQL, Redis, private MinIO, Mailpit, Caddy, and independent media/scene workers are running; API/PostgreSQL/Redis/Mailpit health checks pass.

NEXT STEP:
- Await owner-controlled Hostinger/registry/DNS/CDN/Stripe/SMTP/monitoring inputs and licensed/legal approvals, then execute the evidence map phase by phase. If credentials are supplied, begin with immutable image build/push, host audit, deploy-mode validation, and provider provisioning; do not skip directly to launch.

PRODUCTION-READINESS GAPS:
- `docs/INTERNAL_GAP_AUDIT.md` now records all focused repository-owned implementation/browser gates as proved locally; provider deployment and owner/content/legal evidence remain external and unclaimed.
- The six owner/provider/content/legal blockers remain tracked separately in `docs/LAUNCH_CHECKLIST.md`.
