# Internal production-readiness gap audit

This audit maps unresolved repository work to explicit Command A requirements. It is not
an owner-input list and it must not be used to turn local evidence into launch approval.

| Requirement | Current evidence | Determination | Required closure evidence |
| --- | --- | --- | --- |
| §48 large-file resumable/chunked upload, progress, pause/resume where supported | PostgreSQL-owned private multipart session, 16 MiB signed parts, server-authoritative part listing/completion, browser pause/resume, final SHA-256/container validation | **PROVED LOCALLY** — real MinIO interruption/resume API and Chromium acceptance pass | Provider Spaces acceptance remains deployment evidence |
| §49/§58 CDN protected delivery | Short-lived source/session HMAC path, pre-cache edge verification, immutable source/object cache key, secret API origin with current rights/session revalidation, private Spaces, range bypass, CORS/CSP integration | **PROVED LOCALLY** — API and edge tests cover valid/tampered/expired grants, cache hit, origin secrecy, object ownership, content types, and ranges | CDN deployment, DNS, secrets, cache observation and two-region public-edge acceptance remain external evidence |
| §58 robust workers with retry/idempotency | PostgreSQL row-locked UUID leases, heartbeats, stale-owner rejection, bounded recovery and attempt exhaustion for media and Scene jobs | **PROVED LOCALLY** | Provider failure/capacity drill remains external evidence |
| §48 direct-to-storage and integrity | Short-lived private presigned upload plus persisted multipart, declared and stored SHA-256/size/container verification | **PROVED LOCALLY** — both upload paths converge on the same final integrity boundary | Provider Spaces acceptance remains deployment evidence |
| Command B §54 risky-feature flags | Typed synchronized API/web flags; router/action denial; navigation/control removal; request-proxy 404; strict owner input dependencies; repeatable all-off staging rebuild with automatic enabled-stack restoration | **PROVED LOCALLY** — enabled/disabled production builds, API/web regressions, HTTP checks, and 4/4 deployed desktop/mobile Chromium checks cover screenshots, responsive navigation absence, customer/API 404s, console errors, failed requests, and server errors | Repeat the gate against the provisioned Hostinger production candidate before launch |
| Command A §63 / production policy routes | Eight-document tracked package, approved-only routes/footer, request-proxy 404, production content validator and deploy-mode owner gate | **PROVED LOCALLY** — 5 web tests, build, placeholder rejection and isolated HTTP checks pass | Owner/counsel final text, approval metadata and production browser acceptance remain external evidence |
| Command A §63 consent/privacy controls | Default-off analytics consent, ingestion denial, timestamp, raw-event erasure, No Algorithm Discover projection and account UI | **PROVED LOCALLY** — API lifecycle and 2/2 deployed desktop/mobile Chromium journeys prove default-off UI, denial, explicit grant, accepted event persistence, withdrawal erasure, renewed denial, No Algorithm persistence, screenshot, and clean console/network behavior | Repeat against the provisioned Hostinger production candidate and obtain owner/counsel privacy approval before launch |
| Command A §62 upload malware integration | Persisted quarantine verdict, EICAR scanner, ClamAV INSTREAM adapter, outage retry, Studio scan status/retry controls, processing clean-verdict boundary and preflight PING | **PROVED LOCALLY** — real MinIO, protocol/config/UI tests, reversible migration, 75 API regressions and 8 web checks pass | Private production clamd, definitions/update policy, isolation and production control-file acceptance remain external evidence |
| Command A §60 concurrent stream limits | Atomic per-account Redis admission keyed by device session, entitlement-derived cap, bounded expiry/refresh, API-proxy and CDN-origin lease checks, fail-closed outage behavior, actionable watch UI | **PROVED LOCALLY** — admission/refresh/expiry/invalid-entitlement checks, 77 API and 14 web regressions, and a live two-device desktop/mobile denial journey pass | Provider Valkey failure drill and real multi-device CDN cache/grant acceptance remain deployment evidence |
| Command A §60–61 geo/territory rights | `country_code` remains production origin; explicit allowlists cover title/edition; signed assertions propagate through every title-bearing customer surface; playback/media/CDN grants and caches bind country; trusted public ingress replaces client values with provider-derived signatures | **PROVED LOCALLY** — all Studio controls, cross-service predicates, unknown/allowed catalog and club behavior, assertion tamper/age tests, server forwarding, lease retention, media recheck, CDN region-tamper rejection, and geo-ingress spoof/unknown tests pass | Deploy the real geo edge, bind the direct Hostinger origin/DNS/secrets, and capture multi-country public allowed/denied evidence |

The Hostinger migration added and locally proved eight-artifact digest-only releases/rollback,
host hardening, off-site backup/media-copy procedures, private Studio origin enforcement,
private monitoring, blackbox/TLS/origin-denial checks, and fail-closed configuration validation.
Caddy, storage, Node Exporter, and Blackbox Exporter are now first-party nonroot artifacts built
from exact reviewed sources; all four local candidates scan with 0 critical/0 high findings. The
complete external artifact mapping now lives in `docs/HOSTINGER_EVIDENCE_MAP.md`.

The final adapted-Caddy audit found and closed an ingress-ordering defect before production
handoff. Hostinger application routes now use an order-preserving policy: origin admission is
evaluated first, private Studio/admin admission second, and application proxies last. The real
Caddy 2.11.4 JSON adaptation is machine-checked for this order as well as both independent
secrets; a regression test rejects the former proxy-before-denial shape.

The same ordered edge policy now mitigates the outstanding MinIO application advisories by
denying unsigned-payload trailers, Snowball auto-extraction, S3 Select, replication
server-side-encryption metadata, and the internal storage REST namespace before the MinIO proxy.
Policy tests and a real hardened edge/storage integration prove the denial responses while signed
S3 create/version/put/get behavior remains available. This is defense in depth around the final
Community release, not evidence that the vulnerable upstream feature paths were repaired.

No known repository-owned implementation or browser-evidence gap remains after this focused
audit. This determination is limited to current source, tests, actual Caddy 2.11.4, Prometheus
3.14.0-distroless, and Blackbox Exporter 0.28.0 configuration validation, and the restored HTTPS
staging topology. It does not close or reduce
the six owner/provider/content/legal blockers in the launch checklist, and any failed production
rehearsal reopens the corresponding implementation audit.
