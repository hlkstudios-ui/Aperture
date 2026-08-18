# Hostinger Production Evidence Map

Last audited: 2026-08-18

This maps every machine-readable launch-evidence kind to its repository procedure and the
external artifact still required. It is not evidence that production exists. References must
identify immutable, access-controlled artifacts without credentials, cookies, signed URLs,
customer data, or recovery codes.

| Gate / evidence kind | Repository procedure or verifier | Required production artifact | Current state |
| --- | --- | --- | --- |
| `production_admin/admin_mfa_enrollment` | Studio MFA flow and browser acceptance; `docs/PRODUCTION_HANDOFF.md` | Audit-event reference plus owner-controlled recovery-storage attestation | External |
| `production_admin/recovery_login` | Recovery-code login tests and Admin Lockout runbook | One-use recovery login/sign-out evidence from approved disposable exercise | External |
| `production_admin/admin_acceptance` | Command B final scenario; deployed browser suite | Owner Studio login/create/upload/process/preview/publish/schedule/sign-out artifact | External |
| `infrastructure_cdn/provider_resources` | `deploy/production/hostinger/validate_config.py`, `validate_topology.py`, host audit | Hostinger VPS/resource IDs, private DB/Redis/MinIO/ClamAV checks, firewall and encryption evidence | External |
| `infrastructure_cdn/dns_tls` | private Blackbox contract and `public_edge_smoke.py` | Public DNS/certificate evidence for web, origin, storage, and media hostnames | External |
| `infrastructure_cdn/public_edge` | geo-edge tests, origin-secret denial, public smoke | Deployed Worker routing plus allowed/denied/spoofed/unknown-country results | External |
| `infrastructure_cdn/cdn_authorization` | CDN worker tests and CDN README acceptance | Grant/tamper/expiry/cache/range/origin-secret evidence from two regions | External |
| `infrastructure_cdn/authenticated_media_acceptance` | full generated-media Playwright journey | Production upload → scan → transcode → private adaptive playback artifact | External |
| `infrastructure_cdn/billing_acceptance` | mocked Stripe/webhook integration and preflight | Stripe live-mode approved disposable checkout/webhook lifecycle references | External |
| `infrastructure_cdn/smtp_acceptance` | staging Mailpit reset journey and SMTP preflight | Verified production delivery plus one-use reset result | External |
| `infrastructure_cdn/customer_data_acceptance` | export/deletion API and browser acceptance | Approved disposable production export and confirmed deletion references | External |
| `infrastructure_cdn/browser_matrix` | Playwright Chromium/Firefox/WebKit matrix | Same release tested against public production edge and retained report | External |
| `recovery/backup_job` | Hostinger `operations.sh backup`, freshness metric and alert | Successful private off-site dump/manifest plus retention/versioning evidence | External |
| `recovery/isolated_restore` | guarded `operations.sh restore` and restore verifier | Separate empty `aperture_restore_*` result with digest/head/table parity | External |
| `recovery/rpo_rto` | Backup/restore runbooks | Measured provider RPO/RTO against owner-approved targets | External |
| `rollback/deployment_active` | digest-only Compose/topology audit and production preflight | Exact API/web/backup digests, migration head, ready state and smoke report | External |
| `rollback/traffic_rollback` | `hostinger_rollback.py --mode inspect/execute` | Dual-approved known-good digest set and completed rollback execution record | External |
| `rollback/post_rollback_acceptance` | public smoke and bad-deployment runbook | Healthy preflight/smoke/product subset plus complete alert-window observation | External |
| `observability/error_tracking` | production DSN validation and structured logging | Synthetic error received without PII in owner-approved project | External |
| `observability/alert_delivery` | 17 Prometheus rules, private host/API/blackbox collectors | Synthetic critical alerts received, acknowledged, and resolved | External |
| `observability/on_call` | monitoring handoff and incident runbooks | Primary/secondary routes, escalation timers, and tabletop evidence | External |
| `content_legal/catalog_rights` | title/edition/territory/window enforcement | Licensor/source/territory/window/asset-right records for every launch title | Owner/legal |
| `content_legal/catalog_workflow` | Command B 24-step final scenario | Licensed production title completing the entire workflow twice | Owner/legal + external |
| `content_legal/policy_approval` | approved-only policy routes and build/deploy gates | Final eight-document package, approver role, timestamps and counsel references | Owner/legal |

## Release binding

Before collecting any row, bind the record to:

- the non-secret release ID and infrastructure version;
- deployment UTC time;
- migration head `b7e4c91d2a60`;
- exact web, API, media-worker, scene-worker, and backup image digests;
- the Hostinger configuration revision and unresolved-risk register.

Run `deploy/production/launch_evidence.py --mode verify` only after all references and human
approvals exist. `evidence_complete` still requires accountable human launch approval and does
not authorize traffic by itself.
