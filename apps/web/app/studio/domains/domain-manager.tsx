"use client";

import { useActionState, useEffect, useRef, useState } from "react";

import {
  addDomainAction,
  makePrimaryDomainAction,
  refreshDomainAction,
  removeDomainAction,
  usePlatformDomainAction,
  type DomainActionState,
} from "./actions";
import type { DomainDnsRecord, SiteDomain, SiteDomainCollection } from "./domain-types";
import styles from "./domains.module.css";

const INITIAL_ACTION_STATE: DomainActionState = { sequence: 0, error: "", notice: "" };
const PRIMARY_ELIGIBLE_STATUSES = new Set(["active"]);
const TERMINAL_STATUSES = new Set(["removing", "removed", "disabled"]);

type StatusPresentation = {
  label: string;
  detail: string;
  tone: "live" | "ready" | "waiting" | "attention" | "quiet";
};

function statusKey(value: string): string {
  return value.trim().toLocaleLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
}

function statusPresentation(value: string, primary: boolean): StatusPresentation {
  const key = statusKey(value);
  if (primary && key === "active") {
    return { label: "Live · Primary", detail: "Customers can enter through this domain.", tone: "live" };
  }
  const known: Record<string, StatusPresentation> = {
    provisioning: { label: "Preparing setup", detail: "Secure routing and DNS instructions are being prepared.", tone: "waiting" },
    pending: { label: "Pending DNS", detail: "Add the records below at your DNS provider.", tone: "waiting" },
    pending_dns: { label: "Pending DNS", detail: "Add the records below at your DNS provider.", tone: "waiting" },
    pending_verification: { label: "Checking ownership", detail: "The required DNS records are not visible yet.", tone: "waiting" },
    verifying: { label: "Checking ownership", detail: "The required DNS records are being checked.", tone: "waiting" },
    pending_tls: { label: "Certificate issuing", detail: "Ownership is verified; secure HTTPS is being prepared.", tone: "waiting" },
    certificate_pending: { label: "Certificate issuing", detail: "Ownership is verified; secure HTTPS is being prepared.", tone: "waiting" },
    pending_edge: { label: "Connecting edge", detail: "DNS is verified; secure customer routing is being prepared.", tone: "waiting" },
    ready: { label: "Connection check required", detail: "DNS and HTTPS appear ready. Check the connection to finish secure routing.", tone: "waiting" },
    verified: { label: "Connection check required", detail: "DNS and HTTPS appear ready. Check the connection to finish secure routing.", tone: "waiting" },
    certificate_ready: { label: "Connection check required", detail: "DNS and HTTPS appear ready. Check the connection to finish secure routing.", tone: "waiting" },
    active: { label: "Connected", detail: "This domain is connected and can become the primary front door.", tone: "ready" },
    failed: { label: "Needs attention", detail: "Review the DNS records and check the connection again.", tone: "attention" },
    error: { label: "Needs attention", detail: "Review the DNS records and check the connection again.", tone: "attention" },
    disabled: { label: "Disabled", detail: "This domain is not accepting customer traffic.", tone: "quiet" },
    removing: { label: "Removing", detail: "Routing and certificate cleanup are in progress.", tone: "quiet" },
    removed: { label: "Removed", detail: "This domain is no longer connected.", tone: "quiet" },
  };
  return known[key] ?? {
    label: value.trim().replaceAll("_", " ") || "Status unavailable",
    detail: "Check the connection for the latest DNS and certificate state.",
    tone: "quiet",
  };
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "Not checked yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not checked yet";
  return `${new Intl.DateTimeFormat("en-CA", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(date)} UTC`;
}

function failureMessage(value: string | null | undefined): string | null {
  if (!value) return null;
  const known: Record<string, string> = {
    provider_timeout: "The domain provider timed out. Check the connection again in a moment.",
    provider_unavailable: "The domain provider is temporarily unavailable.",
    provider_unauthorized: "The domain service needs its provider credentials refreshed.",
    provider_rate_limited: "The domain provider is busy. Wait briefly, then check again.",
    provider_hostname_not_found: "The provider no longer has this hostname. Edge access has been withdrawn.",
    edge_reconciliation_required: "Routing could not be confirmed. The hosted Aperture address remains available while an administrator reconciles the edge.",
    turnstile_unavailable: "CAPTCHA hostname setup is unavailable, so this domain has not been activated.",
    turnstile_hostname_quota: "The configured CAPTCHA widget has reached its hostname limit.",
  };
  return known[value] ?? "The latest connection check needs attention. Try again or review the deployment logs.";
}

function ActionMessage({ state }: { state: DomainActionState }) {
  return <div className={styles.actionMessage} aria-live="polite" aria-atomic="true">
    {state.error ? <p className={styles.error} role="alert">{state.error}</p> : null}
    {state.notice ? <p className={styles.success} role="status">{state.notice}</p> : null}
  </div>;
}

function UsePlatformForm({
  platformHostname,
  revision,
}: {
  platformHostname: string;
  revision: number;
}) {
  const [state, action, pending] = useActionState(
    usePlatformDomainAction,
    INITIAL_ACTION_STATE,
  );
  return <form action={action} className={styles.platformForm}>
    <input name="platform_hostname" type="hidden" value={platformHostname} />
    <input name="revision" type="hidden" value={revision} />
    <button className="studio-secondary" disabled={pending} type="submit">
      {pending ? "Switching..." : "Use Aperture-hosted address as primary"}
    </button>
    <small>Connected custom domains stay available as alternate entrances.</small>
    <ActionMessage state={state} />
  </form>;
}

function AddDomainForm({
  available,
  platformHostname,
}: {
  available: boolean;
  platformHostname: string;
}) {
  const [state, action, pending] = useActionState(addDomainAction, INITIAL_ACTION_STATE);
  const formRef = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (state.notice) formRef.current?.reset();
  }, [state.notice, state.sequence]);

  return <form action={action} className={styles.addForm} ref={formRef}>
    <label htmlFor="new-storefront-domain">
      <span>Customer domain</span>
      <input
        autoCapitalize="none"
        autoComplete="url"
        id="new-storefront-domain"
        inputMode="url"
        maxLength={253}
        name="hostname"
        placeholder="watch.example.com"
        required
        spellCheck={false}
        disabled={!available || pending}
        aria-describedby="new-storefront-domain-help"
      />
      <small id="new-storefront-domain-help">{available
        ? "Enter the domain only. Do not include https://, a path, or a port."
        : `Custom-domain infrastructure is not enabled on this deployment. ${platformHostname} remains fully usable.`}</small>
    </label>
    <button className="studio-primary" disabled={pending || !available} type="submit">
      {pending ? "Adding domain…" : available ? "Add domain" : "Custom domains unavailable"}
    </button>
    {!available ? <p className={styles.availabilityNotice} role="status">
      <strong>Aperture-hosted access stays available.</strong>
      <span>Customers can keep using {platformHostname}; this does not block launch or setup.</span>
    </p> : null}
    <ActionMessage state={state} />
  </form>;
}

function CopyRecordButton({ record }: { record: DomainDnsRecord }) {
  const [message, setMessage] = useState("Copy value");
  async function copy() {
    try {
      await navigator.clipboard.writeText(record.value);
      setMessage("Copied");
    } catch {
      setMessage("Select and copy");
    }
  }
  return <button
    aria-label={`Copy ${record.type.toUpperCase()} value for ${record.name}`}
    className={styles.copyButton}
    onClick={copy}
    type="button"
  >{message}</button>;
}

function DnsRecords({ domain }: { domain: SiteDomain }) {
  if (!domain.dns_records.length) {
    return <div className={styles.recordsEmpty}>
      <strong>DNS instructions are being prepared</strong>
      <p>Check the connection in a moment. The exact records will appear here when available.</p>
    </div>;
  }
  const includesHttpValidation = domain.dns_records.some(
    (record) => record.type.toUpperCase() === "HTTP",
  );
  return <section className={styles.records} aria-labelledby={`dns-records-${domain.id}`}>
    <div className={styles.sectionHeading}>
      <div><p>Registrar-neutral setup</p><h3 id={`dns-records-${domain.id}`}>DNS records</h3></div>
      <span>{domain.dns_records.length} record{domain.dns_records.length === 1 ? "" : "s"}</span>
    </div>
    <p className={styles.recordsHelp}>At the company where this domain’s DNS is managed, create the CNAME and TXT records exactly as shown. Some providers call an apex CNAME an ALIAS, ANAME, or flattened CNAME.{includesHttpValidation ? " For an HTTP record, serve the response body at the exact validation URL shown." : ""}</p>
    <div className={styles.recordGrid}>
      {domain.dns_records.map((record, index) => {
        const recordType = record.type.toUpperCase();
        const isHttp = recordType === "HTTP";
        return <article className={styles.recordCard} key={`${record.type}:${record.name}:${index}`}>
          <header><strong>{recordType}</strong><span>{record.purpose || (recordType === "TXT" || isHttp ? "Ownership" : "Routing")}</span></header>
          <dl>
            <div><dt>{isHttp ? "Validation URL" : "Name / host"}</dt><dd><code>{record.name}</code></dd></div>
            <div><dt>{isHttp ? "Response body" : "Value / target"}</dt><dd><code>{record.value}</code></dd></div>
          </dl>
          <CopyRecordButton record={record} />
        </article>;
      })}
    </div>
  </section>;
}

function DomainOperationForm({ domain, operation, available }: {
  domain: SiteDomain;
  operation: "refresh" | "make-primary";
  available: boolean;
}) {
  const serverAction = operation === "refresh" ? refreshDomainAction : makePrimaryDomainAction;
  const [state, action, pending] = useActionState(serverAction, INITIAL_ACTION_STATE);
  const terminal = TERMINAL_STATUSES.has(statusKey(domain.status));
  const canMakePrimary = PRIMARY_ELIGIBLE_STATUSES.has(statusKey(domain.status)) && !domain.is_primary;
  const disabled = pending || terminal || !available || (operation === "make-primary" && !canMakePrimary);
  return <form action={action} className={styles.operationForm}>
    <input name="domain_id" type="hidden" value={domain.id} />
    <input name="hostname" type="hidden" value={domain.hostname} />
    <input name="revision" type="hidden" value={domain.revision} />
    <button className={operation === "make-primary" ? "studio-primary" : "studio-secondary"} disabled={disabled} type="submit">
      {pending
        ? operation === "refresh" ? "Checking…" : "Activating…"
        : operation === "refresh" ? "Check connection" : domain.is_primary ? "Current primary" : "Make primary"}
    </button>
    <ActionMessage state={state} />
  </form>;
}

function RemoveDomainForm({ domain, available }: { domain: SiteDomain; available: boolean }) {
  const [confirmation, setConfirmation] = useState("");
  const [state, action, pending] = useActionState(removeDomainAction, INITIAL_ACTION_STATE);
  const isExact = confirmation.trim().toLocaleLowerCase().replace(/\.$/, "") === domain.hostname.toLocaleLowerCase();
  const removalUnavailable = !available || TERMINAL_STATUSES.has(statusKey(domain.status));
  return <details className={styles.removePanel}>
    <summary>{removalUnavailable ? "Removal unavailable" : "Remove domain"}</summary>
    {removalUnavailable ? <p>{available
      ? "This domain is already being disconnected."
      : "Domain changes are unavailable until custom-domain infrastructure is enabled. The Aperture-hosted address remains usable."}</p> : <>
      <p>This disconnects the storefront from <strong>{domain.hostname}</strong>. It does not delete customers, catalog content, or brand settings.</p>
      {domain.is_primary ? <p><strong>The Aperture-hosted address will become the primary front door.</strong> Customers using it can continue normally.</p> : null}
      <form action={action}>
        <input name="domain_id" type="hidden" value={domain.id} />
        <input name="hostname" type="hidden" value={domain.hostname} />
        <input name="revision" type="hidden" value={domain.revision} />
        <label htmlFor={`remove-domain-${domain.id}`}>
          Type <strong>{domain.hostname}</strong> to confirm
          <input
            autoCapitalize="none"
            autoComplete="off"
            disabled={removalUnavailable || pending}
            id={`remove-domain-${domain.id}`}
            name="confirmation"
            onChange={(event) => setConfirmation(event.target.value)}
            spellCheck={false}
            value={confirmation}
          />
        </label>
        <button className={styles.dangerButton} disabled={!isExact || removalUnavailable || pending} type="submit">
          {pending ? "Removing…" : "Remove domain"}
        </button>
        <ActionMessage state={state} />
      </form>
    </>}
  </details>;
}

function DomainCard({ domain, operationsAvailable }: {
  domain: SiteDomain;
  operationsAvailable: boolean;
}) {
  const presentation = statusPresentation(domain.status, domain.is_primary);
  return <article className={styles.domainCard} data-primary={domain.is_primary || undefined}>
    <header className={styles.domainHeader}>
      <div>
        <p>{domain.is_primary ? "Primary customer entrance" : "Connected domain"}</p>
        <h2>{domain.hostname}</h2>
      </div>
      <span className={styles.status} data-tone={presentation.tone}><i />{presentation.label}</span>
    </header>
    <p className={styles.statusDetail}>{failureMessage(domain.failure_reason) || presentation.detail}</p>
    <dl className={styles.domainFacts}>
      <div><dt>Ownership</dt><dd>{domain.ownership_status?.replaceAll("_", " ") || (domain.verified_at ? "Verified" : "Pending")}</dd></div>
      <div><dt>HTTPS certificate</dt><dd>{domain.certificate_status?.replaceAll("_", " ") || (PRIMARY_ELIGIBLE_STATUSES.has(statusKey(domain.status)) ? "Ready" : "Pending")}</dd></div>
      <div><dt>Last checked</dt><dd>{formatDate(domain.last_checked_at)}</dd></div>
    </dl>
    <DnsRecords domain={domain} />
    <div className={styles.domainActions}>
      <DomainOperationForm domain={domain} operation="refresh" available={operationsAvailable} />
      <DomainOperationForm domain={domain} operation="make-primary" available={operationsAvailable} />
    </div>
    {!operationsAvailable ? <p className={styles.activationHint}>Connection checks, primary changes, and removal are paused until custom-domain infrastructure is enabled.</p> : null}
    {!domain.is_primary && !PRIMARY_ELIGIBLE_STATUSES.has(statusKey(domain.status)) ? <p className={styles.activationHint}>Make primary unlocks after Check connection reports the domain as connected.</p> : null}
    <RemoveDomainForm domain={domain} available={operationsAvailable} />
  </article>;
}

export function DomainManager({ collection, loadError = "" }: {
  collection: SiteDomainCollection;
  loadError?: string;
}) {
  const orderedDomains = [...collection.domains].toSorted((left, right) => {
    if (left.is_primary !== right.is_primary) return left.is_primary ? -1 : 1;
    return left.hostname.localeCompare(right.hostname);
  });
  const primary = orderedDomains.find((domain) => domain.is_primary || domain.id === collection.primary_domain_id);
  const platformHostname = collection.platform_hostname || "apertures.online";
  const frontDoor = primary?.hostname || platformHostname;

  return <div className={styles.workspace}>
    <section className={styles.frontDoor} aria-labelledby="front-door-title">
      <div>
        <p className="eyebrow">Current front door</p>
        <h2 id="front-door-title">{frontDoor}</h2>
        <span>{primary ? "Custom domain live" : "Platform domain in use"}</span>
      </div>
      <div className={styles.frontDoorCopy}>
        <p>{primary
          ? `Customers can use ${frontDoor}. The application, catalog, accounts, and playback system behind it remain Aperture infrastructure.`
          : "Add and verify a domain below to give customers an address that matches the published brand."}</p>
        <p className={styles.hostedFallback}><strong>Safe hosted address:</strong> {platformHostname} remains available. A custom domain is optional and never blocks launch.</p>
        {primary ? <UsePlatformForm
          platformHostname={platformHostname}
          revision={collection.revision}
        /> : <p className={styles.platformPrimary}><strong>Current primary:</strong> the Aperture-hosted address is already in use.</p>}
        <a href={`https://${frontDoor}`} rel="noreferrer" target="_blank">Open customer site <span aria-hidden="true">↗</span></a>
      </div>
    </section>

    <section className={styles.onboarding} aria-labelledby="add-domain-title">
      <div>
        <p className="eyebrow">Identity · Address</p>
        <h2 id="add-domain-title">Add a customer domain</h2>
        <p>{collection.custom_domains_available
          ? "Use an address your audience recognizes. We will provide exact CNAME and TXT records; your registrar and nameservers can remain where they are."
          : `Custom-domain infrastructure is not enabled on this deployment. The Aperture-hosted address ${platformHostname} remains fully usable.`}</p>
      </div>
      <AddDomainForm
        available={collection.custom_domains_available}
        platformHostname={platformHostname}
      />
      <ol className={styles.steps} aria-label="Domain connection process">
        <li><span>01</span><div><strong>Add</strong><p>Enter the customer-facing domain.</p></div></li>
        <li><span>02</span><div><strong>Connect</strong><p>Publish the supplied DNS records.</p></div></li>
        <li><span>03</span><div><strong>Verify</strong><p>Wait for ownership and HTTPS readiness.</p></div></li>
        <li><span>04</span><div><strong>Activate</strong><p>Choose the ready domain as primary.</p></div></li>
      </ol>
    </section>

    {loadError ? <section className={styles.loadError} role="alert">
      <strong>Domain controls are temporarily unavailable</strong>
      <p>{loadError}</p>
      <p>No domain settings were changed. Reload this page when the domain service is available.</p>
    </section> : null}

    <section className={styles.domainList} aria-labelledby="connected-domains-title" aria-busy={false}>
      <div className={styles.listHeading}>
        <div><p className="eyebrow">Managed entrances</p><h2 id="connected-domains-title">Your domains</h2></div>
        <span>{orderedDomains.length} configured</span>
      </div>
      {loadError ? null : orderedDomains.length
        ? orderedDomains.map((domain) => <DomainCard
            domain={domain}
            key={domain.id}
            operationsAvailable={collection.custom_domains_available}
          />)
        : <div className={styles.empty}>
            <span aria-hidden="true">◎</span>
            <h3>{collection.custom_domains_available ? "No custom domains yet" : "Custom domains are not enabled"}</h3>
            <p>{collection.custom_domains_available
              ? "The platform address remains available. Add your first customer domain above when you are ready."
              : `${platformHostname} remains fully usable as the customer-facing Aperture address.`}</p>
          </div>}
    </section>
  </div>;
}
