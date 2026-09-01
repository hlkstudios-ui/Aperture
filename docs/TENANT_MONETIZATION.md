# Tenant monetization architecture

## Status and decision

This document defines the target operating model for businesses that rent the Aperture software
and then sell access to their own viewers. It is an architecture and launch contract, not a claim
that multi-tenant provisioning or tenant payments are implemented today. The current repository
and production topology remain one owner-controlled installation with payments disabled.

The initial commercial model is **one isolated application cell per tenant**. Every cell runs the
same reviewed Aperture release, but it has an independent data plane, runtime identity, secrets,
payment-provider connection, and public routing boundary. A control plane may automate cell
provisioning and lifecycle operations; it must not turn multiple businesses into aliases for one
unpartitioned application database.

The marketplace identity, template/version/agreement, rental-intent, and future trusted resolver
boundaries are defined in the [platform control-plane contract](PLATFORM_CONTROL_PLANE.md). This
document remains authoritative for cell isolation and the tenant-owned viewer-commerce flow.

This model is intentionally different from adding a `tenant_id` field to only a few tables. The
current application has single-installation assumptions across identity, Studio, catalog, media,
billing, playback, analytics, storage, caches, and queues. A partial shared-data conversion would
create cross-business disclosure and payment-misdirection risks.

## Two strictly separate money flows

The platform and storefront money flows have different sellers, customers, credentials, records,
and support responsibilities. They must never share a merchant account, checkout session, webhook
secret, subscription record, balance, payout control, or revenue total.

### 1. Platform rental

The Aperture platform operator charges a tenant for use of the software and managed cell. The
platform operator is the seller for this transaction. Platform plans, invoices, payment-provider
credentials, subscription lifecycle, refunds, taxes, and revenue reporting belong to a separate
control-plane billing domain.

A missed platform-rental payment may suspend creation of new tenant checkouts or eventually suspend
the cell under an approved grace policy. It must not silently rewrite viewer payment records,
initiate a payout from the tenant's provider account, or delete tenant data.

### 2. Tenant storefront sales

A viewer buys a subscription from the tenant whose storefront they opened. The tenant chooses the
supported payment provider, sets its viewer plans and prices, accepts the provider's terms, handles
refunds and disputes, and receives provider payouts into its verified payout destination. Viewer
subscriptions and entitlements exist only inside that tenant's cell.

For Stripe, the intended first integration is Stripe Connect with **direct charges on the connected
tenant account**. The connected tenant is treated by Aperture as the merchant of record for its
viewer sales. Aperture does not use its platform Stripe balance as a transit account and does not
create payouts from a shared platform balance. The initial model also does not take an application
fee from viewer charges; adding one later requires a new commercial, accounting, policy, and legal
review.

The exact merchant, tax, dispute, refund, negative-balance, and statement-descriptor responsibilities
depend on the provider product, connected-account configuration, tenant country, and applicable law.
The provider configuration and tenant agreement must be reviewed before a paid launch; the label in
this document is not legal or tax advice.

Every new tenant may be offered payment setup, but payment acceptance is not automatic. The provider
may require identity and business verification, supported-country and currency checks, sanctions or
risk review, bank verification, and specific payment capabilities. A provider denial, restriction,
or pending KYC state must leave checkout disabled. Aperture cannot override provider underwriting or
promise that every tenant will be approved.

## Provider and financial-data boundary

Tenant owners must complete hosted provider onboarding or an OAuth-style provider connection. They
must not paste raw secret API keys, webhook secrets, card data, or bank account and routing numbers
into an Aperture form. Provider-hosted pages collect regulated identity, card, mandate, and bank
details directly.

A cell may persist only the minimum non-secret provider state required to operate, such as:

- the provider name and opaque connected-account identifier;
- an opaque secret-manager reference when a server credential is unavoidable;
- capability, KYC, charges, and payouts status returned by the provider;
- opaque customer, price, subscription, invoice, charge, refund, and event references;
- currency, amount, lifecycle state, and timestamps needed for the tenant ledger; and
- the last successful connection and webhook reconciliation timestamps.

Any provider token that must exist server-side belongs in a managed secret boundary with envelope
encryption, tenant-scoped access, rotation, revocation, and access auditing. It must not enter Git,
the shared repository `.env`, browser JavaScript, application logs, analytics, support exports,
database snapshots as plaintext, or audit details. Webhook payload retention must be minimized and
must not become an alternate store for payment credentials or identity documents.

A Stripe Connect platform secret is a platform-wide credential, not a tenant-cell secret. It must
never be copied into every cell because a compromised cell could then act on other connected
accounts. Before multi-cell payment launch, Connect operations must run through a central payment
broker that alone holds the platform credential, authenticates a cell-scoped workload identity, and
checks the immutable cell-to-connected-account mapping on every request. A provider-issued
credential may live inside a cell only when its scope is technically restricted to that tenant's
merchant account and that restriction is acceptance-tested. The current single-cell Connect
onboarding foundation is disabled in production and does not yet provide this broker.

### What "direct deposit" means

In this product, **provider payout to the tenant's verified bank account** is called a payout, not a
viewer checkout method. The provider owns payout scheduling and bank verification; Aperture records
status and references but does not collect bank instructions or move money itself.

If a tenant wants viewers to pay from a bank account, that is a provider-supported bank-payment
method such as an applicable ACH, ACSS, or SEPA product. It may be offered only through a provider
adapter that handles authorization, mandates, settlement delay, returns, and webhook reconciliation.
An emailed transfer, bank screenshot, memo, or manually typed confirmation must never automatically
grant a streaming entitlement. A future offline bank-transfer workflow would require an explicit
pending-payment ledger, authorized reconciliation, reversal handling, and an audit trail.

## Cell isolation contract

Each tenant cell is identified by an immutable internal UUID and a unique stable slug. Changing the
public business name does not change either identifier.

At minimum, a cell owns all of the following:

| Boundary | Required isolation |
| --- | --- |
| PostgreSQL | A separate database and workload credential. No tenant application role may connect to another cell's database. |
| Redis | A separate service or enforceable ACL/keyspace identity for sessions, rate limits, playback leases, OAuth state, caches, and queues. Redis database numbers alone are not a security boundary. |
| Object storage | A separate bucket or a tenant-prefix credential enforced by IAM. The cell identity cannot list, read, overwrite, or delete another cell's prefix. |
| Workers and queues | Cell-scoped media and scene queues, workers, leases, retry limits, and dead-letter/incident handling. A job contains the cell identity and is verified against its database record before object access. |
| Runtime secrets | Independent session, edge, CDN, SMTP, CAPTCHA, OAuth, error-tracking, storage, database, and cell-scoped provider/broker secret references with separate rotation history. A platform-wide provider credential is never installed in a tenant cell. |
| Payment provider | One tenant-owned connected merchant account or equivalent connection, a broker-enforced cell/account mapping, isolated webhook endpoint identity, and tenant-only ledger. |
| Brand and policy | Independent published brand, legal-owner information, policy package, locale, catalog, rights records, and Studio owner. |
| Observability | Cell-labeled metrics and alerts with access controls. Logs must not expose provider secrets, bank data, cookies, or signed media URLs. |
| Backup and recovery | Cell-specific backup inventory, retention policy, restore evidence, RPO/RTO, legal hold, and deletion schedule. |

Shared immutable application images are expected. Shared data credentials, mutable volumes, provider
accounts, session namespaces, and unscoped administrative queries are prohibited. Where a managed
service hosts more than one cell, provider-enforced identities and policies must preserve the same
deny-by-default boundary and must be acceptance-tested from each identity.

Tenant content rights are not inherited from Aperture or another tenant. Each cell must retain its
own authoritative rights evidence, territories, windows, allowed editions and assets, and takedown
owner before publishing content or accepting money for access.

## Hosted and custom domains

Every tenant receives a default hosted front door:

```text
https://{slug}.apertures.online
```

The root `apertures.online` hostname remains the Aperture-operated storefront and must not select a
tenant from browser input. Slugs must be unique, normalized, protected from reserved infrastructure
names, and mapped by the trusted edge/control plane to exactly one cell. Unknown, suspended,
provisioning, and decommissioned mappings fail closed.

A tenant may optionally attach one or more verified custom domains registered with any supported
registrar. A custom domain and the tenant's hosted subdomain route to the same cell. The hosted
subdomain remains a recovery front door unless the tenant lifecycle policy explicitly suspends the
whole cell. Domain removal changes routing only and must not delete the tenant's customers, media,
subscriptions, provider connection, or cell.

The current in-application domain feature attaches aliases to one installation; it does not perform
the cross-cell selection described here. Multi-business routing requires a control-plane registry
that maps each admitted hostname to a cell, publishes the edge route only after the cell is healthy,
and withdraws edge admission before decommissioning. See [Optional customer domains](CUSTOM_DOMAINS.md)
for the existing one-installation DNS and TLS behavior.

Customer and Studio sessions remain host-bound and cell-bound. Password-reset, OAuth, checkout,
billing-portal, and provider onboarding returns must be validated against an active hostname for the
same cell. No caller-supplied body, query parameter, or unsigned header may select a cell.

## Payment adapter contract

Stripe Connect is the first intended tenant storefront adapter, not a provider-specific shortcut
inside account, entitlement, or Studio code. A future provider adapter must support the following
server-side contract or explicitly report a capability as unavailable:

1. Start provider-hosted connection/onboarding for a known cell and validated return origin.
2. Read connection, KYC, charges, payouts, country, currency, and payment-method capability status.
3. Create or synchronize tenant-owned products and recurring prices using cell-scoped idempotency.
4. Create viewer checkout and billing-portal sessions on the tenant merchant account.
5. Verify webhook authenticity before parsing any event and resolve the cell from the trusted
   connection/endpoint, not from event metadata alone.
6. Reconcile customer, subscription, invoice, payment, refund, dispute, and cancellation events
   idempotently into the tenant cell's ledger and entitlements.
7. Revoke or disconnect the provider connection without erasing historical financial records.
8. Expose opaque references and safe status only; never return credentials or bank data to the web
   application.

Provider event identifiers, customer references, price codes, and idempotency keys are unique within
the tuple `(cell_id, provider, connection_id)`. A webhook signed by Tenant A's endpoint must never
look up Tenant B's user, plan, subscription, or entitlement, even if metadata or opaque references
are malformed or reused. Unknown providers and missing capabilities fail closed.

Payout initiation should normally stay in the tenant's provider dashboard. If a future adapter
supports an Aperture payout control, it requires separate step-up authorization, provider capability
checks, balance and currency validation, cell-scoped idempotency, and an immutable audit record. It
must never access the platform-rental merchant balance.

## Provisioning contract

The control plane must make provisioning idempotent and resumable. A requested cell is not publicly
admitted until every required step succeeds:

1. Reserve the immutable cell ID, normalized slug, hosted hostname, owner identity, rental plan,
   region, and lifecycle record.
2. Create cell-scoped secret references and least-privilege database, Redis, object-storage, backup,
   queue, worker, monitoring, deployment, and payment-broker identities.
3. Create the empty data services, enable encryption/versioning/retention as applicable, and prove
   that each workload identity is denied access to a synthetic neighboring cell.
4. Pin an immutable, tested Aperture release manifest and apply its forward migration to the cell
   database.
5. Provision the tenant owner through the audited offline/hosted owner flow, require MFA, and record
   recovery custody without storing recovery secrets in the control plane.
6. Publish the default brand draft, legal/policy setup state, and explicit feature/payment defaults.
   Checkout stays disabled.
7. Start the cell services and workers, then run cell-local readiness, migration-head, storage,
   queue, authentication, catalog, media, backup, and cross-cell denial checks.
8. Publish the hosted-subdomain edge mapping last. Optional custom-domain admission follows its own
   ownership and TLS verification.
9. If requested, begin provider-hosted onboarding. Enable viewer checkout only after live-mode,
   webhook, KYC, charges, payout, currency, policy, and lifecycle acceptance gates pass.
10. Write a secret-free provisioning acceptance record containing the cell ID, release digests,
    infrastructure references, migration head, checks performed, owners, and timestamps.

Provisioning states must distinguish at least requested, provisioning, awaiting owner action, ready,
suspended, decommissioning, failed, and decommissioned. Retrying a step may reuse only resources
whose recorded ownership and configuration match the cell. It must not guess ownership from a name.

## Deployment, rollback, suspension, and removal

Application code is built once into immutable images and promoted to cells by digest. Cell-specific
configuration and secrets are injected at runtime and are never baked into an image. A rollout is
serialized per cell and records its release, predecessor, migration head, evidence, and outcome.

For each cell, a deployment must:

- verify the target cell and its workload identities before mutation;
- take and verify the required off-site backup before a risky release or migration;
- render only that cell's runtime and secret references;
- run the migration once, wait for every service and worker, and execute private and public smoke
  checks through that cell's hosted hostname;
- leave other cells untouched if the candidate fails; and
- publish acceptance only after the edge, application, worker, storage, and provider boundaries agree.

Rollouts should use cohorts and a synthetic canary cell before broad promotion. A cell may remain on
the accepted predecessor while another cell is upgraded; the control plane must expose version drift
and supported-version deadlines.

Rollback restores the prior compatible application image and runtime for the affected cell only.
Database migrations are forward-only and must remain compatible with the accepted predecessor during
the rollback window. A rollback does not rotate or replace tenant payment connections, rewrite
financial history, reverse database data, or restore a backup over live data without a separately
authorized recovery operation.

Suspension withdraws new checkout and, according to the approved grace policy, public edge admission
while retaining data and evidence. It does not equal deletion. Decommissioning withdraws every domain
first, revokes runtime and provider credentials, stops workers, takes the required final export or
backup, observes retention and legal holds, and only then performs an approved, cell-targeted deletion.
Recursive or wildcard deletion across a shared storage root is prohibited.

The repository's current continuous-deployment controller manages one production installation. It
does not yet implement the per-cell orchestration in this section. Its immutable-release, backup-first,
fail-closed, forward-migration, and audited-rollback principles remain requirements for the future
control plane; see [Continuous deployment](CONTINUOUS_DEPLOYMENT.md).

## Paid-tenant launch gates

A real tenant may accept viewer payments only when evidence confirms all of the following:

- the platform-rental and tenant-storefront merchant accounts, credentials, ledgers, webhooks, and
  reports are separate;
- the cell has independent DB, Redis, storage/IAM, worker/queue, secret, backup, and observability
  boundaries, including explicit neighboring-cell denial tests;
- the hosted subdomain routes only to that cell, and each optional custom domain is ownership- and
  TLS-verified before admission;
- customer and Studio sessions, OAuth state, reset links, checkout returns, and billing portals are
  bound to the same cell and verified hostname;
- the tenant's provider connection is live, KYC-approved, charges-enabled, payouts-enabled where
  required, and limited to supported country, currency, and payment-method capabilities;
- signed webhook delivery, duplicate delivery, delayed/out-of-order delivery, invalid signatures,
  refunds, disputes, payment failure, cancellation, renewal, and entitlement removal have passed
  acceptance without cross-cell lookup;
- no raw API key, webhook secret, card data, identity document, mandate, or bank detail appears in
  the browser, database plaintext, source tree, logs, analytics, support export, or audit details;
- tenant plans, taxes, cancellation/refund terms, privacy terms, and customer support ownership are
  approved and published for that tenant;
- every paid title has tenant-specific content-rights and territory evidence and a tested takedown
  path;
- per-cell backup restore, application rollback, provider disconnection, suspension, and final
  decommissioning have been rehearsed with secret-free evidence;
- quotas, abuse controls, monitoring receivers, incident ownership, and customer-impact escalation
  are active; and
- an accountable platform operator and tenant owner approve the exact cell, release, provider mode,
  policy versions, and launch timestamp.

"Eligible for monetization" means the setup capability is available to the tenant. It never means
checkout is enabled before these gates or that Aperture fabricates provider approval, payment,
settlement, payout, rights, or legal status.

## Longer-term shared-database option

A future shared-database SaaS architecture is a separate migration project, not an optimization that
may be enabled by routing more hostnames to the current installation. Before any two unrelated
businesses share an application database, the design must include tenant-scoped identities and
memberships, mandatory server-derived tenant context, tenant keys on every owned row, tenant-inclusive
foreign and unique constraints, PostgreSQL row-level security for ordinary runtime roles, scoped
admin/support tools, tenant-aware jobs, storage/IAM, caches, CDN grants, analytics, audits, backups,
and payment connections.

The migration must backfill the existing Aperture installation as one legacy tenant, validate all
cross-table ownership, adversarially test every read/write/export/delete/webhook/worker path, enable
row-level enforcement before admitting a second hostname, and canary a synthetic second tenant before
real data. A brand row, payment-provider form, custom-domain record, UI filter, or application-only
query convention is not a tenancy boundary.

Until that complete migration has independent review and acceptance evidence, isolated cells remain
the required production model for unrelated tenant businesses.
