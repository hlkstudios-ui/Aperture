"use client";

import { useActionState } from "react";

import {
  beginStripeConnectAction,
  refreshMonetizationStatusAction,
  type MonetizationActionState,
} from "./actions";
import type {
  MonetizationConnectionStatus,
  ViewerPlan,
  ViewerMonetizationRecord,
} from "./monetization-types";
import { ViewerPlanManager } from "./viewer-plan-manager";
import styles from "./monetization.module.css";

const initialActionState: MonetizationActionState = { sequence: 0, error: "", notice: "" };

const futureProviders = [
  {
    name: "PayPal",
    capabilities: ["Hosted checkout planned", "Recurring billing planned", "Provider-managed payouts planned"],
    reason: "The PayPal adapter has not been installed or verified for this release.",
  },
  {
    name: "Additional providers",
    capabilities: ["Capability-based adapter", "Verified webhooks", "Provider-managed settlement"],
    reason: "More providers can be added without exposing credentials in Studio, after each adapter passes payment and reconciliation review.",
  },
] as const;

type StatusCopy = { label: string; detail: string; tone: "quiet" | "waiting" | "attention" | "ready" };

function connectionPresentation(status: MonetizationConnectionStatus): StatusCopy {
  const presentations: Record<MonetizationConnectionStatus, StatusCopy> = {
    disabled: {
      label: "Provider unavailable",
      detail: "Stripe Connect is disabled in this Aperture runtime. An Aperture operator must enable the server-side integration before hosted onboarding can begin. The storefront remains free.",
      tone: "quiet",
    },
    not_connected: {
      label: "Not connected",
      detail: "Stripe onboarding has not started. Viewer payments cannot be accepted.",
      tone: "quiet",
    },
    onboarding_required: {
      label: "Setup in progress",
      detail: "Return to Stripe to finish the information it requires, then refresh the status here.",
      tone: "waiting",
    },
    restricted: {
      label: "Needs attention",
      detail: "Stripe reports outstanding requirements. Charges or payouts remain unavailable.",
      tone: "attention",
    },
    ready: {
      label: "Provider ready",
      detail: "Stripe reports the connection ready. This alone does not turn on a subscription paywall.",
      tone: "ready",
    },
  };
  return presentations[status];
}

function formatUpdatedAt(value: string | null): string {
  if (!value) return "Not checked yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unavailable";
  return `${new Intl.DateTimeFormat("en-CA", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(date)} UTC`;
}

function Feedback({ state }: { state: MonetizationActionState }) {
  return <div className={styles.feedback} aria-live="polite" aria-atomic="true">
    {state.error ? <p className={styles.error} key={`error-${state.sequence}`} role="alert">{state.error}</p> : null}
    {state.notice ? <p className={styles.success} key={`notice-${state.sequence}`} role="status">{state.notice}</p> : null}
  </div>;
}

function Fact({ label, value, tone }: { label: string; value: string; tone?: "yes" | "no" }) {
  return <div><dt>{label}</dt><dd data-tone={tone}>{value}</dd></div>;
}

function humanRequirement(value: string): string {
  const normalized = value.trim().replaceAll("_", " ").replaceAll(".", " · ");
  return normalized ? normalized.charAt(0).toLocaleUpperCase() + normalized.slice(1) : "Provider action required";
}

function connectedAccountLabel(value: string | null): string {
  if (!value) return "Not connected";
  const suffix = value.slice(-4);
  return `Stripe account ••••${suffix}`;
}

function ProviderFacts({ record }: { record: ViewerMonetizationRecord }) {
  return <dl className={styles.providerFacts}>
    <Fact label="Account" value={connectedAccountLabel(record.connected_account_id)} />
    <Fact label="Provider details" value={record.details_submitted ? "Submitted" : "Incomplete"} tone={record.details_submitted ? "yes" : "no"} />
    <Fact label="Charges" value={record.charges_enabled ? "Enabled by Stripe" : "Not enabled"} tone={record.charges_enabled ? "yes" : "no"} />
    <Fact label="Payouts" value={record.payouts_enabled ? "Enabled by Stripe" : "Not enabled"} tone={record.payouts_enabled ? "yes" : "no"} />
    <Fact label="Provider environment" value={record.livemode === true ? "Live" : record.livemode === false ? "Test" : "Not reported"} />
    <Fact label="Prepared active plans" value={String(record.active_plan_count)} />
    <Fact label="Last checked" value={formatUpdatedAt(record.updated_at)} />
  </dl>;
}

function StripeProviderCard({ record }: { record: ViewerMonetizationRecord }) {
  const [connectState, connectAction, connectPending] = useActionState(
    beginStripeConnectAction,
    initialActionState,
  );
  const [refreshState, refreshAction, refreshPending] = useActionState(
    refreshMonetizationStatusAction,
    initialActionState,
  );
  const presentation = connectionPresentation(record.connection);
  const runtimeDisabled = record.connection === "disabled";
  const started = record.provider === "stripe_connect"
    && !["disabled", "not_connected"].includes(record.connection);
  const runtimeHelpId = "stripe-runtime-requirement";

  return <article className={styles.providerCard} data-featured="true">
    <header className={styles.providerHeader}>
      <div><span>{runtimeDisabled ? "Unavailable in this runtime" : "Available provider"}</span><h3>Stripe Connect</h3></div>
      <span className={styles.providerStatus} data-tone={presentation.tone}><i />{presentation.label}</span>
    </header>
    <p className={styles.providerDetail}>{presentation.detail}</p>
    <ul className={styles.capabilities} aria-label="Stripe adapter capabilities">
      <li>Hosted provider onboarding</li>
      <li>Subscription checkout planned, not enabled</li>
      <li>Verified provider status</li>
      <li>Provider-managed bank payouts after paid release</li>
    </ul>
    <ProviderFacts record={record} />
    {record.requirements_due.length ? <section className={styles.requirements} aria-labelledby="stripe-requirements-title">
      <h4 id="stripe-requirements-title">Outstanding provider requirements</h4>
      <ul>{record.requirements_due.map((requirement) => <li key={requirement}>
        <strong>{humanRequirement(requirement)}</strong>
        <span>Continue hosted Stripe setup to review this requirement.</span>
      </li>)}</ul>
    </section> : null}
    <div className={styles.providerActions}>
      <form action={connectAction}>
        <button
          aria-describedby={runtimeDisabled ? runtimeHelpId : undefined}
          className="studio-primary"
          disabled={connectPending || runtimeDisabled}
          type="submit"
        >
          {runtimeDisabled ? "Stripe setup unavailable" : connectPending ? "Opening Stripe..." : started ? "Continue hosted Stripe setup" : "Set up Stripe securely"}
        </button>
        {runtimeDisabled ? <small id={runtimeHelpId}>Server-side Stripe Connect setup must be enabled by your Aperture operator.</small> : null}
        <Feedback state={connectState} />
      </form>
      <form action={refreshAction}>
        <button className="studio-secondary" disabled={refreshPending || !started} type="submit">
          {refreshPending ? "Checking..." : "Refresh provider status"}
        </button>
        {!started && !runtimeDisabled ? <small>Available after hosted setup begins.</small> : null}
        <Feedback state={refreshState} />
      </form>
    </div>
    <p className={styles.providerBoundary}><strong>No API-key or bank form.</strong> Stripe collects identity and payout details on its own hosted pages. Aperture stores only the connection and status needed to prepare a future paid-storefront release.</p>
  </article>;
}

function AccessModePanel({ record }: { record: ViewerMonetizationRecord }) {
  return <section className={styles.accessPanel} aria-labelledby="viewer-access-title">
    <div className={styles.sectionHeading}>
      <div><p className="eyebrow">Viewer access</p><h2 id="viewer-access-title">Free remains the safe default.</h2></div>
      <span data-mode={record.access_mode}>{record.access_mode === "free" ? "Free access" : "Subscription required"}</span>
    </div>
    <p>{record.access_mode === "free"
      ? "Viewers are not required to pay. Connecting or completing Stripe onboarding never changes this setting by itself."
      : "The server reports subscription-required access. Provider webhooks—not redirect pages—must remain authoritative for paid access."}</p>
    {record.access_mode === "free" ? <div className={styles.activationLocked} role="status">
      <strong>Subscription activation is not available in this release.</strong>
      <p>You can prepare the provider connection, but the storefront stays free until the verified checkout, webhook, entitlement, and playback gates are released together.</p>
    </div> : null}
  </section>;
}

export function MonetizationSetup({
  record,
  plans = [],
}: {
  record: ViewerMonetizationRecord;
  plans?: ViewerPlan[];
}) {
  return <div className={styles.workspace}>
    <section className={styles.moneyBoundary} aria-labelledby="money-boundary-title">
      <div><p className="eyebrow">Two separate relationships</p><h2 id="money-boundary-title">Prepare future viewer revenue separately from your Aperture rental.</h2></div>
      <div className={styles.moneyFlows}>
        <article><span>01</span><div><strong>Your Aperture rental</strong><p>What you pay to use the Aperture system. It is not configured on this page.</p></div></article>
        <article><span>02</span><div><strong>Your customer payments</strong><p>This page prepares the provider connection for a future paid release. It does not enable checkout or route viewer revenue yet.</p></div></article>
      </div>
    </section>

    {record.notice ? <div className={styles.notice} role="status"><strong>Payment setup status</strong><p>{record.notice}</p></div> : null}

    <AccessModePanel record={record} />

    <ViewerPlanManager plans={plans} />

    <section aria-labelledby="payment-provider-title" className={styles.providersSection}>
      <div className={styles.sectionHeading}>
        <div><p className="eyebrow">Provider adapters</p><h2 id="payment-provider-title">Prepare a future payment provider.</h2></div>
        <span>{record.connection === "disabled" ? "Provider runtime disabled" : "Available to set up"}</span>
      </div>
      <p className={styles.sectionIntro}>This release can prepare hosted onboarding only. Customer checkout and viewer-revenue routing are not enabled; they become effective only after the separately reviewed paid-checkout release. Provider approval, supported countries, and live capabilities remain provider decisions.</p>
      <div className={styles.providerGrid}>
        <StripeProviderCard record={record} />
        {futureProviders.map((provider, index) => {
          const reasonId = `future-provider-${index}-reason`;
          return <article className={styles.providerCard} key={provider.name}>
            <header className={styles.providerHeader}><div><span>Future adapter</span><h3>{provider.name}</h3></div><span className={styles.providerStatus} data-tone="quiet"><i />Unavailable</span></header>
            <ul className={styles.capabilities} aria-label={`${provider.name} planned capabilities`}>
              {provider.capabilities.map((capability) => <li key={capability}>{capability}</li>)}
            </ul>
            <button aria-describedby={reasonId} className="studio-secondary" disabled type="button">Adapter unavailable</button>
            <p className={styles.unavailableReason} id={reasonId}>{provider.reason}</p>
          </article>;
        })}
      </div>
    </section>

    <section className={styles.bankBoundary} aria-labelledby="bank-payout-title">
      <span aria-hidden="true">BANK</span>
      <div><p className="eyebrow">Settlement</p><h2 id="bank-payout-title">Bank payout is handled by the payment provider.</h2><p>When the separately reviewed paid release is enabled, your bank account will be a payout destination inside the provider. It is not an alternative Aperture checkout method, and Aperture does not ask you to type bank details here.</p></div>
    </section>
  </div>;
}
