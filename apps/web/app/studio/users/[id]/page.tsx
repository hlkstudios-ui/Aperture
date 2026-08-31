import Link from "next/link";
import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { apiGatewayPath } from "@/app/lib/api-gateway";
import { StudioShell } from "@/app/studio/components/studio-shell";
import { deleteCustomer, revokeCustomerSessions, updateCustomerState } from "./actions";

type Customer = { id: string; email: string; is_active: boolean; created_at: string; profile_count: number; active_session_count: number; profiles: Array<{id:string;name:string;is_kids:boolean;language:string}>; sessions:Array<{id:string;user_agent:string|null;ip_address:string|null;last_seen_at:string;revoked_at:string|null}>; subscriptions:Array<{id:string;plan:string;status:string;provider:string;current_period_end:string|null;cancel_at_period_end:boolean}>; entitlements:Array<{key:string;value:Record<string, unknown>;source:string}> };

export default async function UserPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [admin, customer] = await Promise.all([requireAdminSession(), adminCatalogFetch<Customer>(`/admin/support/users/${id}`)]);
  return <StudioShell admin={admin} active="users" eyebrow="Customer support" title={customer.email} actions={<Link href="/studio/users">Back to users</Link>}>
    <section className="analytics-kpis" aria-label="Customer summary"><article><small>Account</small><strong>{customer.is_active ? "Active" : "Disabled"}</strong></article><article><small>Profiles</small><strong>{customer.profile_count}</strong></article><article><small>Active sessions</small><strong>{customer.active_session_count}</strong></article></section>
    <div className="editor-columns"><section className="editor-panel"><p className="eyebrow">Safe support actions</p><h2>Account access</h2>
      <form action={updateCustomerState}><input type="hidden" name="id" value={id}/><input type="hidden" name="is_active" value={customer.is_active ? "false" : "true"}/><label>Reason <input required minLength={3} maxLength={500} name="reason" /></label><button type="submit">{customer.is_active ? "Disable account" : "Reactivate account"}</button></form>
      <form action={revokeCustomerSessions}><input type="hidden" name="id" value={id}/><label>Reason <input required minLength={3} maxLength={500} name="reason" /></label><button type="submit">Revoke all sessions</button></form>
      <p><a href={apiGatewayPath(`/admin/support/users/${id}/export`)}>Export portable customer JSON</a></p>
      <details><summary>Authorized permanent deletion</summary><p>This permanently removes the account and profile-owned records. Export first. Only proceed against an approved privacy request or documented legal basis.</p><form action={deleteCustomer}><input type="hidden" name="id" value={id}/><label>Exact customer email <input type="email" name="confirmation_email" required /></label><label>Type DELETE CUSTOMER <input name="confirmation_phrase" pattern="DELETE CUSTOMER" required /></label><label>Reason <textarea name="reason" minLength={10} maxLength={500} required /></label><label>Authorization or request reference <input name="authorization_reference" minLength={3} maxLength={200} required /></label><button type="submit">Permanently delete customer</button></form></details>
    </section><section className="editor-panel"><p className="eyebrow">Billing</p><h2>Subscriptions and entitlements</h2>{customer.subscriptions.map(s=><p key={s.id}><strong>{s.plan}</strong><br/>{s.status} via {s.provider}</p>)}{!customer.subscriptions.length&&<p>None</p>}<dl>{customer.entitlements.map(e=><div key={`${e.key}-${e.source}`}><dt>{e.key}</dt><dd>{JSON.stringify(e.value)}</dd></div>)}</dl></section></div>
    <div className="editor-columns"><section className="editor-panel"><h2>Profiles</h2><ul>{customer.profiles.map(p=><li key={p.id}>{p.name} · {p.language}{p.is_kids ? " · Kids" : ""}</li>)}</ul></section><section className="editor-panel"><h2>Recent devices</h2><ul>{customer.sessions.slice(0,10).map(s=><li key={s.id}>{s.user_agent ?? "Unknown device"} · {s.ip_address ?? "Unknown IP"} · {s.revoked_at ? "Revoked" : "Active"}</li>)}</ul></section></div>
  </StudioShell>;
}
