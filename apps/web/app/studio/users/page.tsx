import Link from "next/link";
import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { StudioShell } from "@/app/studio/components/studio-shell";

type User = { id: string; email: string; is_active: boolean; created_at: string; profile_count: number; active_session_count: number; subscription_status: string | null; plan_name: string | null };
type Result = { items: User[]; total: number };

export default async function UsersPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const q = (await searchParams).q ?? "";
  const [admin, result] = await Promise.all([
    requireAdminSession(),
    adminCatalogFetch<Result>(`/admin/support/users?q=${encodeURIComponent(q)}`),
  ]);
  return <StudioShell admin={admin} active="users" eyebrow="Customer support" title="Users">
    <p className="editor-intro">Search customer accounts, inspect entitlements, revoke sessions, and control access. Every support mutation is reason-gated and audited.</p>
    <form className="studio-toolbar" method="get"><label>Search customers <input name="q" defaultValue={q} placeholder="email address" /></label><button type="submit">Search</button></form>
    <section className="editor-panel"><p className="eyebrow">{result.total} customers</p><div className="table-scroll"><table><thead><tr><th>Email</th><th>State</th><th>Profiles</th><th>Sessions</th><th>Subscription</th><th /></tr></thead><tbody>
      {result.items.map((user) => <tr key={user.id}><td>{user.email}</td><td>{user.is_active ? "Active" : "Disabled"}</td><td>{user.profile_count}</td><td>{user.active_session_count}</td><td>{user.plan_name ? `${user.plan_name} · ${user.subscription_status}` : "None"}</td><td><Link href={`/studio/users/${user.id}`}>Open</Link></td></tr>)}
    </tbody></table></div>{!result.items.length && <p className="studio-empty-inline">No customers match this search.</p>}</section>
  </StudioShell>;
}
