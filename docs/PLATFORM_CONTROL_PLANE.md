# Platform control-plane contract

## Purpose and authority

This document defines the boundary between the Aperture marketplace and the independently operated
Aperture tenant cells. It is the authoritative contract for platform identity, template rentals,
future cell provisioning, and hostname resolution. It complements, rather than replaces,
[Tenant monetization architecture](TENANT_MONETIZATION.md), which remains authoritative for tenant
commerce, provider handling, cell isolation, and paid-tenant acceptance.

This is a target architecture with a deliberately narrow foundation slice. It does not claim that
platform billing, tenant-cell provisioning, a cross-cell hostname resolver, or multi-tenant
production operations exist. The current Aperture application remains one owner-controlled cell.
Payments remain disabled. Unrelated businesses must not be placed in that cell by adding branding
rows, hostnames, or partially scoped `tenant_id` columns.

The selected commercial topology is one isolated application cell per tenant. Every cell runs the
same canonical, reviewed Aperture application images; it does not receive a copied or independently
edited source tree. This preserves one maintainable template implementation without treating a
shared database as an isolation boundary. A shared-database/RLS design is a separate future
migration described in [Tenant monetization architecture](TENANT_MONETIZATION.md#longer-term-shared-database-option).

## Three authoritative domains

| Domain | Seller and users | Owns | Must not own |
| --- | --- | --- | --- |
| Platform core | Aperture is the seller; renters use platform accounts | Marketplace, platform identity, template registry, versioned rental agreements, legal acceptance, rental intents, future platform billing, cell registry/provisioning, platform audit, and superadministration | Cell viewers, tenant catalog/media, tenant viewer subscriptions, tenant payment balances, or tenant payout instructions |
| Tenant cell | The renter operates one isolated Aperture installation; its viewers and cell administrators authenticate there | Brand, policies, catalog, rights, viewers, cell administrators, profiles, media, storage, queues, sessions, analytics, tenant plans, entitlements, backups, and runtime configuration | Platform rental invoices, platform merchant credentials, another cell's data, or the platform session |
| Tenant commerce | The tenant is the seller to its viewers | Provider connection for that tenant, viewer products/prices, checkouts, subscriptions, refunds/disputes, tenant ledger, entitlements, and provider payouts | Platform rental revenue, platform invoices, another tenant's provider account, or a shared platform payout balance |

The two money flows are separate: a renter pays Aperture for the template rental, while a viewer
pays the tenant for access to that tenant's service. Merchant accounts, credentials, checkout
sessions, webhook endpoints/secrets, ledgers, subscriptions, revenue reports, refunds, and audit
records must not cross that boundary.

## Truthful delivery status

| Capability | Current repository truth |
| --- | --- |
| Canonical Aperture cell | Implemented as one single-owner application and one production deployment target; production launch still has external evidence gates. |
| Current custom-domain feature | Aliases verified hostnames to that one installation. It is not a tenant or cell resolver. |
| Existing customer and Studio identity | Implemented for the current cell, with distinct customer and administrator records and cookies. |
| Platform foundation slice | Introduces separate platform account/session and verified-email lifecycle, template/version/agreement, expiring tenant reservation/membership, legal acceptance, unpaid rental-intent, and platform-audit contracts. It is not a provisioned tenant service. |
| Initial template offer | The migration seeds `Apertures` as `preview` only, without a current version, agreement, or price. It is intentionally not rentable until a reviewed publication workflow supplies a complete immutable offer. |
| Platform billing | Disabled and not implemented as an active rental checkout/subscription lifecycle. |
| Tenant cell registry and provisioner | Not implemented. A `TenantReservation` is a logical reservation, not a deployed `TenantCell`. |
| Trusted cross-cell hostname resolver | Not implemented. The existing edge still routes admitted hostnames to one origin. |
| Tenant dashboard and template-generated control panel | Future work. The existing private Studio is not a platform superadmin or a multi-tenant dashboard. |
| Tenant commerce | The current cell has a disabled Stripe Connect onboarding foundation. A central broker, complete webhook/ledger lifecycle, and provider-neutral adapters do not yet exist. |
| Shared-database tenancy/RLS | Not implemented and not the selected near-term production model. |

The foundation records and routes currently live beside the single-cell API and use its database
and runtime. That co-location is acceptable only for developing and proving the no-side-effect
foundation. It is not evidence that the platform control plane is isolated enough to operate real
tenant cells. Before a second business is admitted, control-plane data, credentials, administrative
authority, and failure domain require an explicitly reviewed boundary from every cell workload.

### Transitional co-location gate

`PLATFORM_CONTROL_PLANE_ENABLED` is the fail-closed switch for the transitional, co-located API
surface. It defaults to `false`. When false, the platform authentication and marketplace routers are
not mounted and `/platform/*` is not an alternate way into the cell. Every tenant-cell runtime made
from the canonical Aperture images must keep this flag false, including the current legacy cell.
Copying a platform cookie to a cell must not make the routes appear or authorize anything.

Only a deliberately identified transitional platform deployment may set the flag true, together
with an Aperture-owned origin, the platform host-only cookie, and reviewed platform data/runtime
credentials. When enabled, the current foundation surface consists of separate platform
register/login/session routes, read-only template collection/detail routes, authenticated
rental-intent creation/listing, and the `/marketplace` preview. It has no template publication or
platform-superadmin write surface. The flag controls reachability; it does not turn a shared runtime
or database into a production isolation boundary.

The final architecture moves the platform core into its own service and database credentials,
separate from every tenant cell. Until that separation, a unified migration may leave empty platform
tables in a cell database as a transitional schema artifact, but a cell must never enable the
routers, hold platform sessions or records, or receive platform billing/provisioning credentials.
Migration `20260831_0037` therefore fails before mutation if it finds any platform account or rental
record; migrating a real renter requires an explicit identity-verification and ownership-preserving
runbook rather than an automatic deadline. It locks the transitional platform tables against old
writers before checking emptiness; traffic drain and the emptiness check are deployment gates.
The existing root storefront has not yet been replaced by the marketplace; that cutover and the
hosted location of the legacy Aperture cell are a later routing migration.

After a complete offer is reviewed and published, the first-slice contract permits an authenticated,
email-verified renter to record an agreement-backed rental intent and temporarily reserve a slug.
An active response is `awaiting_payment`, with platform billing disabled, provisioning
`not_started`, domain creation `not_created`, and next action `platform_billing_unavailable`. If the
reservation deadline passes before the future billing flow completes, the immutable intent becomes
`expired`, its slug is released, and replaying its original idempotency key returns that same terminal
record. Those states are product truth, not temporary UI copy. The seeded preview alone cannot
create an intent.

## Identity, authorization, and cookie boundaries

The platform and a tenant cell are different security principals even when the same human uses both.

1. A renter authenticates to the marketplace as a `PlatformAccount`. Its opaque platform-session
   cookie is accepted only by the platform boundary; staging and production require the
   `__Host-` prefix.
2. A viewer authenticates inside one cell through the existing customer identity and
   `aperture_session` cookie. Viewer identity never authorizes a platform rental or another cell.
3. A cell administrator authenticates inside that cell through its administrator boundary and
   `aperture_admin_session` cookie. A platform membership is not itself a cell administrator session.
4. A platform superadministrator is a separately authorized operator identity. It must not reuse an
   ordinary renter membership or an ordinary cell administrator session.

All three cookie names remain distinct. Production cookies are `Secure`, `HttpOnly`, appropriately
`SameSite`, and host-only: no parent-domain `Domain` attribute may make a platform or one cell's
cookie visible to every `*.apertures.online` tenant. A custom domain and its hosted subdomain are
separate browser origins and do not silently share cookies. Moving between them requires
reauthentication or a future short-lived, single-use handoff bound to the exact account, cell,
audience, destination hostname, nonce, and expiry.

The transitional platform router cannot be enabled in staging or production unless CAPTCHA is
required and the platform cookie uses the `__Host-` prefix. This blocks tenant-child-host cookie
tossing and makes automated registration/mail abuse protection a configuration invariant.

Password reset, email verification, OAuth state/callbacks, tenant-provider onboarding, checkout
returns, and billing portals must be bound to the initiating security domain and an active hostname.
No body field, query parameter, unsigned header, cookie from another host, or client-provided
`tenant_id` may select or change the tenant context.

A `TenantMembership` authorizes a platform account to manage a logical tenant reservation/rental in
the platform. It does not authorize direct queries against cell data. Future cross-boundary actions
must use a narrowly scoped service identity or a short-lived audience-bound command, and must be
audited on both sides.

## Foundation records and invariants

The names below match the control-plane foundation contract. They must not be confused with current
cell-domain models such as customer `User`, cell `Admin`, `Subscription`, or `SiteDomain`.

### Platform identity

- `PlatformAccount` is the renter identity. Email is normalized and unique; passwords retain the
  existing Argon2id policy.
- `PlatformSession` stores only a token hash, has a bounded expiry and revocation time, and records
  limited device metadata. Raw session tokens never enter the database, logs, analytics, or audits.
- `PlatformEmailVerificationToken` stores only a one-use SHA-256 token digest and an explicit
  delivery lifecycle. Same-account confirmation uses an authenticated restricted session. A
  mailbox owner opening the link in another browser may instead claim the unverified identity by
  passing CAPTCHA, choosing a new strong password, and consuming the token; that transition revokes
  every prior session, so a third party cannot retain credentials after pre-registering the email.
- Registration commits the account, restricted session, staged `pending_delivery` token, and audit
  before attempting delivery. Registration and resend promote a staged token only after successful
  delivery; delivery failure terminalizes only that staged token and, for resend, preserves the
  prior active link. A short delivery lease lets requests and maintenance retire work abandoned by
  a crashed sender. Raw tokens are returned only in development/test and never enter persistence or
  audit data.
- An unverified session may browse the marketplace and manage its verification flow, but the API and
  database both reject rental creation. An unverified registration has a bounded reclamation window;
  reclaiming an expired, unused identity rotates credentials and revokes its old sessions and tokens.
  The account-reclamation deadline and each verification-link deadline are separate, explicit API
  fields and are computed from the database clock.
- Platform registration/login receives its own trusted-origin, CAPTCHA policy, and rate-limit
  namespace. It must not reuse a tenant cell's customer session.

### Template registry and immutable versions

- `PlatformTemplate` is the stable marketplace listing. Its normalized `slug` is unique. Only a
  published template may be rented.
- Publishing requires a `current_version_id`, `current_agreement_version_id`, positive rental price,
  uppercase three-letter currency, and supported billing interval.
- `PlatformTemplateVersion` is append-only after publication. It binds a template version to the
  reviewed `source_commit` and `release_manifest_sha256`, plus a `feature_manifest` and
  `configuration_schema`. These manifests describe supported behavior and configuration; they do
  not contain tenant values or secrets.
- The release hash must refer to the canonical immutable production manifest whose eight image
  references are pinned by digest. A human version label or mutable image tag is not sufficient.
- Changing a template's current version affects only new rental selections. An existing rental
  remains pinned until an explicit, compatible, audited cell rollout succeeds.
- Demo and preview assets are public presentation data only. A demo uses synthetic/read-only data
  and never shares a tenant credential, customer record, provider connection, or production media.

### Agreement, reservation, and rental intent

- `RentalAgreementVersion` contains published immutable terms and a SHA-256 content binding. Draft
  terms do not enter the published-version table.
- `LegalAcceptance` binds one platform account to the exact agreement version and content hash,
  accepted time, and limited request evidence. If terms, price, template version, or material
  configuration changes before intent creation, the platform requires fresh confirmation.
- `TenantReservation` reserves an immutable internal UUID, normalized slug, default hosted hostname,
  and business name. Only an active `reserved` row excludes reuse; expiration makes it `released`
  while retaining the historical row. It is not an application cell, domain admission, resource
  allocation, or claim of ownership over a custom domain.
- `TenantMembership` binds platform accounts to that reservation. The rental contains an exact
  composite foreign-key binding to the owner membership ID, tenant, account, and literal `owner`
  role. Expiration releases that membership; future invitations and role changes require explicit
  authorization and audit rather than client-selected ownership.
- `TemplateRental` is currently an unpaid rental intent. It atomically pins account, reservation,
  template, template version, agreement version, legal acceptance, and the price/currency/interval
  snapshot seen at acceptance. The first-slice states are active `awaiting_payment` and terminal
  `expired`; its reservation deadline and lifecycle timestamps are immutable except for the single
  legal expiration transition.
- `awaiting_payment` grants no application access, platform subscription, cell resources, hostname
  route, viewer checkout, or entitlement. A reserved hosted hostname must not resolve to a tenant
  application.

The template's mutable current pointers and price may change later; the intent snapshot does not.
Historical versions, hashes, acceptances, and price snapshots are retained according to the legal
and accounting policy and are never silently rewritten to match the current listing.

## Billing-disabled lifecycle

The foundation uses three separate state machines rather than one overloaded `status` field:

- **Rental intent:** `awaiting_payment` may move once to terminal `expired`; future
  payment-authoritative states require a reviewed platform-billing tranche.
- **Reservation/cell:** `reserved` becomes `released` when its unpaid intent expires; future cell
  lifecycle is `requested`, `provisioning`,
  `awaiting_owner_action`, `ready`, `suspended`, `decommissioning`, `failed`, and `decommissioned`.
- **Hostname:** future records distinguish reserved, verification pending, active, suspended,
  removing, failed, and removed independently of cell and payment state.

While `BILLING_PROVIDER=disabled`:

1. The platform may present a published template and its agreement.
2. An authenticated, verified account may hold only its configured bounded number of active unpaid
   reservations (one by default) and may record an idempotent legal acceptance, reservation,
   membership, and `awaiting_payment` intent.
3. The platform returns an honest unavailable next action. It does not fabricate checkout success,
   an active rental, or a subscription reference.
4. No provisioner job, database, Redis identity, object bucket, secret, worker, deployment,
   administrator, DNS record, edge mapping, or tenant-provider onboarding is created.
5. Scheduled bounded reconciliation and request-path reconciliation expire overdue intents,
   release their reservation and membership atomically, and append one system audit event.

A future transition out of `awaiting_payment` may occur only after a signed platform-billing event is
reconciled into a separate platform ledger. A checkout redirect or browser success page is never
payment truth. Re-enabling billing requires its own migration, provider adapter, signed webhook,
refund/failure/cancellation handling, policies, tests, and launch approval.

## Idempotency, transactions, and audit

Rental-intent creation is one transaction. The platform either persists the matching reservation,
owner membership, legal acceptance, rental intent, and success audit, or persists none of the
business records. A duplicate replay creates no second success event.

- The client supplies a UUID idempotency key. Uniqueness is scoped to the authenticated platform
  account, not to an email or IP address.
- A canonical SHA-256 request fingerprint binds the normalized request: selected template slug and
  version ID, agreement ID/version/hash, explicit acceptance, business name, and requested slug.
  The price/currency/interval are separately copied from the locked server-side offer into the
  immutable rental snapshot; the browser cannot supply or override them.
- Replaying the same key and fingerprint returns the original result without new rows. The key is
  permanent history: after expiry it returns the original terminal record and never extends or
  recreates it; a genuinely new attempt requires a new UUID key.
- Reusing the same key with a different fingerprint fails with a conflict and creates no resources.
- Concurrent requests for one slug or idempotency key are resolved by database
  uniqueness/foreign-key constraints, not a process-local lock.
- External side effects are prohibited in this slice. Future billing, DNS, secret-manager, storage,
  and provisioner calls require a durable operation/outbox record, a provider idempotency key, an
  expected resource owner, bounded retries, reconciliation, and explicit terminal failure.

`PlatformAuditEvent` is separate from the current cell `AuditLog`. It records actor type/account,
action, outcome, resource type/ID, idempotency key where applicable, timestamp, and bounded
secret-free detail. Legal text, passwords, session tokens, raw provider payloads, payment secrets,
bank/card/identity data, cookies, and signed URLs are not audit detail. Platform audit is append-only
to application actors; later retention/export and tamper-evidence policy must be approved before a
paid launch.

The first slice writes the successful rental-intent event in the business transaction and uses
best-effort audit for platform authentication events. Conflicting or denied rental-intent requests
do not yet have a separate durable audit path. Before billing or provisioning, a transactional audit
or durable security-event channel must cover meaningful denial/failure outcomes without converting
an audit outage into a partial business write or retaining attacker-controlled sensitive content.

## Future tenant cell registry and trusted resolver

`TenantReservation` must eventually be complemented by a real control-plane cell registry. A future
`TenantCell` record should bind an immutable cell UUID and slug to:

- the paid rental and pinned `PlatformTemplateVersion`;
- lifecycle and provisioning revision;
- region and allowlisted private origin identity;
- exact release manifest/digests, configuration-manifest version, and migration head;
- opaque references to cell-specific database, Redis, storage, queues/workers, runtime secrets,
  observability, and backup inventory; and
- secret-free readiness, isolation, deployment, suspension, and recovery evidence.

It stores resource and secret references, not credentials. Provisioning is an idempotent, resumable
state machine that follows the sequence in
[Tenant monetization architecture](TENANT_MONETIZATION.md#provisioning-contract). It applies the
same immutable-release, backup-first, forward-migration, fail-closed, and audited rollback principles
as [Continuous deployment](CONTINUOUS_DEPLOYMENT.md), but serializes and records work per cell. The
current deployment controller remains a one-installation controller and must not be described as
the future cell orchestrator.

The trusted resolver uses only the normalized request `Host` observed at the edge. Its registry maps
each admitted hostname to exactly one active cell, origin, lifecycle, and revision. The edge strips
all client-supplied tenant/cell assertion headers, rejects an unknown or non-active mapping, and
forwards only to the registry's allowlisted healthy origin. If an internal assertion is necessary,
it is short-lived and signed over cell ID, normalized host, origin/audience, revision, issued time,
expiry, and nonce. The cell verifies it before serving the request.

The edge mapping is published last, after the cell and its hosted hostname pass acceptance. It is
withdrawn first during suspension or decommissioning. Eventual-consistency windows must fail closed;
stale state must not reroute a hostname to a different tenant.

## Hosted access, no-custom-domain access, and custom domains

Owning a domain is optional. Every ready tenant receives the durable hosted front door:

```text
https://{slug}.apertures.online
```

This is the supported **no custom domain** option; the renter does not need to register or configure
a domain. In the target topology, the root `apertures.online` marketplace never chooses a tenant
from a query, path, cookie, or browser-supplied ID. Reserved infrastructure labels cannot be tenant
slugs. The current root remains the legacy single-cell storefront until an explicit migration is
accepted; the `/marketplace` preview does not silently change that routing.

A renter may later attach one or more domains registered with any registrar. Registrar choice does
not change the contract: the platform supplies the required DNS target/verification values, proves
ownership, waits for valid TLS, and only then admits the hostname. A custom hostname and the hosted
subdomain resolve to the same cell and pinned rental. The hosted hostname remains a recovery front
door unless the whole cell is suspended.

Removing a custom domain only withdraws that route. It does not delete the cell, viewers, media,
subscriptions, payment connection, or hosted hostname. A hostname cannot be reassigned until removal,
certificate/provider reconciliation, cache/edge withdrawal, and the approved anti-takeover waiting
policy complete. The current `SiteDomain` feature may be reused for DNS/TLS mechanics inside one
cell, but its singleton records and one-origin edge map are not the future control-plane registry.

## Mandatory acceptance gates

Before a second real business or any paid tenant is admitted, automated and reviewed evidence must
prove all of the following:

- **Identity:** platform, cell viewer, cell administrator, and platform-superadmin cookies are
  distinct and host-bound; replay across platform, hosted, custom, and neighboring-cell hosts fails.
- **Runtime exposure:** `PLATFORM_CONTROL_PLANE_ENABLED=false` leaves every tenant cell without
  mounted platform routes, even when the canonical image contains their code; only the separately
  identified platform deployment may enable them, and the final platform service/database is
  independent of cell credentials and data.
- **Authorization:** Tenant A memberships cannot read or mutate Tenant B control-plane records; cell
  admins cannot invoke platform-superadmin operations; support access is separately authorized,
  step-up protected, bounded, and audited.
- **Cell isolation:** synthetic Cell A and Cell B identities are denied access to each other's
  PostgreSQL, Redis/keyspace, object bucket/prefix, queues/jobs, secrets, CDN grants/cache keys,
  observability detail, exports, and backups.
- **Resolver:** unknown, reserved, provisioning, failed, suspended, and decommissioned mappings fail
  closed; spoofed host/assertion headers fail; a hosted and verified custom hostname select exactly
  the same cell; edge publication occurs last and withdrawal first.
- **Idempotency:** duplicate/concurrent rental, payment event, provisioning step, domain operation,
  deployment, suspension, and decommission requests create no duplicate tenant, charge,
  subscription, resource, hostname, or destructive action.
- **Release integrity:** the rented version and every deployed cell resolve to the expected clean
  source commit and exact eight-artifact digest manifest; upgrades are compatible, serialized,
  independently reversible at the application layer, and audited.
- **Secrets and files:** no raw tenant/platform credential enters Git, browser output, database
  plaintext, logs, analytics, support exports, audits, images, or backups; signed media access is
  cell-bound and cross-cell object reads fail.
- **Payments:** disabled mode has no external side effects. Before paid mode, platform and tenant
  merchant accounts, webhooks, ledgers, refunds/disputes, subscriptions, reports, and payouts remain
  separate and pass duplicate, delayed, invalid-signature, and out-of-order event tests.
- **Recovery:** each cell has an off-site backup inventory, encryption/retention evidence, and a
  successful isolated restore that verifies representative identity, catalog, entitlement, and
  private-media behavior in addition to checksum and migration head.
- **Audit and lifecycle:** every privileged transition has actor, authority, target, correlation,
  before/after revision, outcome, and timestamp without secrets; suspension preserves evidence and
  decommissioning follows retention/legal-hold approval before targeted deletion.

Passing current single-cell tests is necessary but cannot substitute for the synthetic two-cell
denial suite.

## End-state renter journey

The intended journey keeps the selected marketplace page underneath the rental modal:

```text
Visitor
  -> Marketplace
  -> Browse/preview a published template
  -> Rent Template (in-place modal)
  -> Read/download the exact versioned agreement and confirm consent
  -> Register or sign in to the platform
  -> Verify the platform email from the same authenticated account
  -> Server revalidates template, version, agreement hash, price, and slug
  -> Create the idempotent awaiting_payment rental intent
  -> Pay Aperture's platform rental fee                         [future]
  -> Reconcile signed payment and provision an isolated cell   [future]
  -> Open tenant dashboard and configure business              [future]
  -> Use hosted subdomain or verify an optional custom domain  [future]
  -> Connect the tenant's provider and pass capability gates   [future]
  -> Define tenant viewer plans/prices and publish              [future]
  -> Viewers pay the tenant; Aperture receives only rental fee  [future]
```

With billing disabled, the current journey intentionally stops at `awaiting_payment`. The renter
must not be redirected to a fake dashboard, an unprovisioned hostname, or the current owner Studio.

## Remaining delivery tranches

1. **Foundation hardening:** finish and migrate the separate platform identity, registry,
   agreement, reservation, intent, and audit slice; add its authenticated APIs, race/idempotency
   tests, marketplace cards, preview/demo, and accessible in-place agreement flow.
2. **Platform billing:** add a platform-owned provider adapter, checkout, signed webhook ledger,
   subscription/failure/refund/cancellation lifecycle, policies, reconciliation, and an explicit
   gate that alone may authorize provisioning.
3. **Cell registry and provisioner:** implement the resource-reference registry, durable operation
   state machine/outbox, synthetic second cell, per-cell deployment inventory, backup/restore, and
   neighboring-cell denial suite.
4. **Trusted routing:** implement server-derived hosted-hostname resolution, signed cell assertions,
   fail-closed lifecycle routing, and edge reconciliation; publish routes only after readiness.
5. **Renter dashboard and template control panel:** add platform memberships/invitations, rental and
   domain status, cell onboarding, and manifest-driven brand/feature/configuration controls without
   permitting source edits or exposing secrets.
6. **Custom-domain control plane:** generalize the proven DNS/TLS mechanics to cell-bound hostname
   records, registrar-neutral instructions, ownership renewal, removal, anti-takeover, and audit.
7. **Tenant commerce:** build the central broker and provider-neutral adapter contract, Stripe
   Connect as the first adapter, provider-hosted onboarding, tenant plans/checkouts/portal, scoped
   webhooks/ledger/entitlements, and KYC/capability/policy launch gates.
8. **Platform operations:** add a separately authorized superadmin, template/version/agreement
   publication, rental support, suspension/decommissioning, version cohorts, audit search/export,
   quotas, observability, incident handling, and evidence-gated paid launch.

Each tranche must extend one authoritative implementation. It must search for and reuse the current
authentication, legal, billing, domain, deployment, storage, audit, and UI primitives where their
security boundary matches; it must not make a cell-local singleton pretend to be a platform-wide
multi-tenant service.
