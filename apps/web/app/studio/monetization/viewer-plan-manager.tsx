"use client";

import { useActionState, useEffect, useRef, useState } from "react";

import {
  archiveViewerPlanAction,
  createViewerPlanAction,
  type ViewerPlanActionState,
} from "./plan-actions";
import type { ViewerPlan } from "./monetization-types";
import styles from "./monetization.module.css";

const initialActionState: ViewerPlanActionState = { sequence: 0, error: "", notice: "" };

function Feedback({ state }: { state: ViewerPlanActionState }) {
  return <div className={styles.feedback} aria-live="polite" aria-atomic="true">
    {state.error ? <p className={styles.error} key={`error-${state.sequence}`} role="alert">{state.error}</p> : null}
    {state.notice ? <p className={styles.success} key={`notice-${state.sequence}`} role="status">{state.notice}</p> : null}
  </div>;
}

function formatPrice(plan: ViewerPlan): string {
  try {
    return new Intl.NumberFormat("en-CA", {
      style: "currency",
      currency: plan.currency,
    }).format(plan.price_cents / 100);
  } catch {
    return `${plan.currency} ${(plan.price_cents / 100).toFixed(2)}`;
  }
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date unavailable";
  return new Intl.DateTimeFormat("en-CA", {
    dateStyle: "medium",
    timeZone: "UTC",
  }).format(date);
}

function PlanFacts({ plan }: { plan: ViewerPlan }) {
  return <dl className={styles.planFacts}>
    <div><dt>Price</dt><dd>{formatPrice(plan)} / {plan.interval}</dd></div>
    <div><dt>Screens</dt><dd>{plan.max_streams}</dd></div>
    <div><dt>Picture</dt><dd>{plan.max_resolution}</dd></div>
    <div><dt>Created</dt><dd>{formatDate(plan.created_at)}</dd></div>
  </dl>;
}

function ArchivePlanForm({ plan }: { plan: ViewerPlan }) {
  const [confirmation, setConfirmation] = useState("");
  const [state, action, pending] = useActionState(
    archiveViewerPlanAction,
    initialActionState,
  );
  return <details className={styles.archivePanel}>
    <summary>Archive plan</summary>
    <p>Archive removes this plan from new viewer choices. It does not rewrite prior subscriptions.</p>
    <form action={action}>
      <input name="plan_id" type="hidden" value={plan.id} />
      <label htmlFor={`archive-plan-${plan.id}`}>
        Type <strong>{plan.code}</strong> to confirm
        <input
          autoCapitalize="none"
          autoComplete="off"
          id={`archive-plan-${plan.id}`}
          name="confirmation"
          onChange={(event) => setConfirmation(event.target.value)}
          spellCheck={false}
          value={confirmation}
        />
      </label>
      <button className={styles.archiveButton} disabled={pending || confirmation !== plan.code} type="submit">
        {pending ? "Archiving..." : "Archive this plan"}
      </button>
      <Feedback state={state} />
    </form>
  </details>;
}

function PlanCard({ plan }: { plan: ViewerPlan }) {
  return <article className={styles.planCard} data-active={plan.is_active || undefined}>
    <header>
      <div><span>{plan.is_active ? "Active viewer plan" : "Archived plan"}</span><h3>{plan.name}</h3></div>
      <code>{plan.code}</code>
    </header>
    <p>{plan.description}</p>
    <PlanFacts plan={plan} />
    {plan.is_active ? <ArchivePlanForm plan={plan} /> : <p className={styles.archivedNote}>Unavailable to new viewers. Create a replacement instead of changing its historic price or terms.</p>}
  </article>;
}

function CreatePlanForm() {
  const [state, action, pending] = useActionState(createViewerPlanAction, initialActionState);
  const formRef = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (state.notice) formRef.current?.reset();
  }, [state.notice, state.sequence]);

  return <form action={action} aria-busy={pending} className={styles.planForm} ref={formRef}>
    <fieldset disabled={pending}>
      <legend>Create a viewer plan</legend>
      <p>Creating a plan does not turn on subscription-required access or customer checkout. Free remains the current storefront default.</p>
      <div className={styles.planFields}>
        <label htmlFor="viewer-plan-code">
          <span>Plan code</span>
          <input autoCapitalize="none" aria-describedby="plan-code-help" id="viewer-plan-code" maxLength={64} name="code" placeholder="cinema-monthly" required spellCheck={false} />
          <small id="plan-code-help">A stable internal label. Spaces become hyphens; archived codes cannot be reused.</small>
        </label>
        <label htmlFor="viewer-plan-name">
          <span>Customer-facing name</span>
          <input autoComplete="off" id="viewer-plan-name" maxLength={120} name="name" placeholder="Cinema Monthly" required />
        </label>
        <label className={styles.fullField} htmlFor="viewer-plan-description">
          <span>Description</span>
          <textarea id="viewer-plan-description" maxLength={500} name="description" placeholder="Describe the access included with this plan." required rows={3} />
        </label>
        <label htmlFor="viewer-plan-price">
          <span>Price</span>
          <input aria-describedby="plan-price-help" id="viewer-plan-price" inputMode="decimal" name="price" placeholder="12.99" required />
          <small id="plan-price-help">Enter a positive amount with up to two decimal places.</small>
        </label>
        <label htmlFor="viewer-plan-currency">
          <span>Currency</span>
          <select aria-describedby="plan-currency-help" defaultValue="CAD" id="viewer-plan-currency" name="currency" required>
            <option value="AUD">AUD — Australian dollar</option>
            <option value="CAD">CAD — Canadian dollar</option>
            <option value="EUR">EUR — Euro</option>
            <option value="GBP">GBP — Pound sterling</option>
            <option value="USD">USD — US dollar</option>
          </select>
          <small id="plan-currency-help">Initial supported set: AUD, CAD, EUR, GBP, and USD. All prices use two decimal places.</small>
        </label>
        <label htmlFor="viewer-plan-interval">
          <span>Billing interval</span>
          <select defaultValue="month" id="viewer-plan-interval" name="interval" required><option value="month">Monthly</option><option value="year">Yearly</option></select>
        </label>
        <label htmlFor="viewer-plan-streams">
          <span>Simultaneous streams</span>
          <input defaultValue="1" id="viewer-plan-streams" inputMode="numeric" max={100} min={1} name="max_streams" required type="number" />
        </label>
        <label htmlFor="viewer-plan-resolution">
          <span>Maximum resolution</span>
          <select defaultValue="1080p" id="viewer-plan-resolution" name="max_resolution" required><option value="720p">720p</option><option value="1080p">1080p</option><option value="4K">4K</option></select>
        </label>
      </div>
    </fieldset>
    <button className="studio-primary" disabled={pending} type="submit">{pending ? "Creating plan..." : "Create active plan"}</button>
    <Feedback state={state} />
  </form>;
}

export function ViewerPlanManager({ plans }: { plans: ViewerPlan[] }) {
  const active = plans.filter((plan) => plan.is_active);
  const archived = plans.filter((plan) => !plan.is_active);
  return <section className={styles.plansSection} aria-labelledby="viewer-plans-title">
    <div className={styles.sectionHeading}>
      <div><p className="eyebrow">Subscription catalogue</p><h2 id="viewer-plans-title">Design what viewers can choose.</h2></div>
      <span>{active.length} active</span>
    </div>
    <div className={styles.immutableNotice} role="note">
      <strong>Published price and terms are immutable.</strong>
      <p>To change price, interval, streams, resolution, or wording, archive the old plan and create a replacement. This protects subscription history from silent changes.</p>
    </div>
    <div className={styles.planWorkspace}>
      <CreatePlanForm />
      <section aria-labelledby="active-viewer-plans-title" className={styles.planList}>
        <div className={styles.planListHeading}><h3 id="active-viewer-plans-title">Active plans</h3><span>{active.length}</span></div>
        {active.length ? active.map((plan) => <PlanCard key={plan.id} plan={plan} />) : <div className={styles.planEmpty}><strong>No active plans yet</strong><p>Create a plan when you are ready to prepare viewer subscriptions. The storefront remains free.</p></div>}
      </section>
    </div>
    <details className={styles.archivedPlans}>
      <summary>Archived plans <span>{archived.length}</span></summary>
      {archived.length ? <div className={styles.archivedGrid}>{archived.map((plan) => <PlanCard key={plan.id} plan={plan} />)}</div> : <p>No plans have been archived.</p>}
    </details>
  </section>;
}
