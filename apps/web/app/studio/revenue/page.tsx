import { randomUUID } from "node:crypto";
import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { StudioShell } from "@/app/studio/components/studio-shell";
import { PayoutForm } from "./payout-form";

type Money = { amount: number; currency: string };
type Snapshot = { provider: string; connection: string; livemode: boolean | null; payouts_enabled: boolean; recorded_receipts: Money[]; recorded_receipts_30d: Money[]; available: Money[]; pending: Money[]; recent_payouts: Array<{ id: string; amount: number; currency: string; status: string; arrival_date: string; created: string }>; notice: string | null };

function money(item: Money) { return new Intl.NumberFormat("en-CA", { style: "currency", currency: item.currency.toUpperCase() }).format(item.amount / 100); }

export default async function RevenuePage() {
  const [admin, snapshot] = await Promise.all([requireAdminSession(), adminCatalogFetch<Snapshot>("/admin/revenue")]);
  const enabled = snapshot.connection === "connected" && snapshot.payouts_enabled && snapshot.available.some((item) => item.amount > 0);
  return <StudioShell admin={admin} active="revenue" eyebrow="Subscription finance" title="Revenue & payouts">
    <section className="revenue-ledger" aria-label="Revenue summary">
      <article><small>Recorded receipts · 30 days</small><strong>{snapshot.recorded_receipts_30d.length ? snapshot.recorded_receipts_30d.map(money).join(" · ") : "$0.00"}</strong><p>Successful invoices recorded by verified webhooks.</p></article>
      <article><small>Available balance</small><strong>{snapshot.available.length ? snapshot.available.map(money).join(" · ") : "—"}</strong><p>Stripe funds currently eligible for payout.</p></article>
      <article><small>Pending settlement</small><strong>{snapshot.pending.length ? snapshot.pending.map(money).join(" · ") : "—"}</strong><p>Funds Stripe has not made available yet.</p></article>
      <article><small>Provider state</small><strong>{snapshot.connection === "connected" ? snapshot.livemode ? "Stripe live" : "Stripe test" : "Not connected"}</strong><p>Test payouts never move real money.</p></article>
    </section>
    {snapshot.notice && <div className="studio-notice"><strong>Revenue pipeline status</strong><p>{snapshot.notice}</p></div>}
    <div className="revenue-workspace">
      <section className="editor-panel"><p className="eyebrow">Cash management</p><h2>Create a payout</h2><p>Funds are sent by Stripe to the external account configured in your Stripe Dashboard. Aperture never collects bank details.</p><PayoutForm balances={snapshot.available} requestId={randomUUID()} enabled={enabled} /></section>
      <section className="editor-panel"><p className="eyebrow">Settlement history</p><h2>Recent payouts</h2>{snapshot.recent_payouts.length ? <ol className="payout-ledger">{snapshot.recent_payouts.map((item) => <li key={item.id}><div><strong>{money(item)}</strong><small>{item.id}</small></div><span className={`catalog-badge ${item.status}`}>{item.status}</span><time dateTime={item.arrival_date}>Arrives {new Date(item.arrival_date).toLocaleDateString("en-CA")}</time></li>)}</ol> : <div className="studio-empty-inline">No Stripe payout history is available.</div>}</section>
    </div>
    <section className="editor-panel revenue-connection-guide"><p className="eyebrow">Activation checklist</p><h2>Connect Stripe without changing code</h2><ol><li><strong>Choose Stripe</strong><span>Set BILLING_PROVIDER=stripe.</span></li><li><strong>Add server credentials</strong><span>Set STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET. Keys never enter the browser.</span></li><li><strong>Register the webhook</strong><span>Point Stripe to /billing/stripe/webhook and subscribe to customer.subscription.*, invoice.paid, and invoice.payment_failed.</span></li><li><strong>Verify the payout destination</strong><span>Configure and verify the bank account in Stripe Dashboard.</span></li><li><strong>Unlock cash management</strong><span>Set STRIPE_PAYOUTS_ENABLED=true only after the test-mode payout succeeds.</span></li></ol></section>
  </StudioShell>;
}
