"use client";

import { useActionState } from "react";
import { createPayoutAction } from "./actions";

type Balance = { amount: number; currency: string };

export function PayoutForm({ balances, requestId, enabled }: { balances: Balance[]; requestId: string; enabled: boolean }) {
  const [state, action, pending] = useActionState(createPayoutAction, { error: "" });
  return <form action={action} className="studio-payout-form">
    <input type="hidden" name="request_id" value={requestId} />
    <label>Available currency<select name="currency" required disabled={!enabled}>{balances.map((item) => <option key={item.currency} value={item.currency}>{item.currency.toUpperCase()} · {(item.amount / 100).toFixed(2)} available</option>)}</select></label>
    <label>Payout amount<input name="amount" inputMode="decimal" placeholder="0.00" required disabled={!enabled} /></label>
    <label className="wide">Type CREATE PAYOUT to confirm<input name="confirmation" autoComplete="off" required disabled={!enabled} /></label>
    <button className="studio-primary" type="submit" disabled={!enabled || pending}>{pending ? "Creating payout…" : "Create Stripe payout"}</button>
    {!enabled && <p className="field-help">Payout creation stays locked until Stripe is connected, an available balance exists, and STRIPE_PAYOUTS_ENABLED=true.</p>}
    {state.error && <p role="alert" className="studio-form-error">{state.error}</p>}
    {state.success && <p role="status" className="studio-form-success">{state.success}</p>}
  </form>;
}
