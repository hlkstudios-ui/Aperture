import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { forwardedGeoHeaders } from "@/app/lib/geo-headers";

export type Plan = { id: string; code: string; name: string; description: string; price_cents: number; currency: string; interval: "month" | "year"; max_streams: number; max_resolution: string };
export type AccountDashboard = {
  email: string;
  subscription: null | { id: string; status: string; provider: string; current_period_start: string | null; current_period_end: string | null; cancel_at_period_end: boolean; plan: Plan };
  entitlements: Array<{ key: string; value: Record<string, unknown>; source: string; starts_at: string | null; ends_at: string | null }>;
  sessions: Array<{ id: string; current: boolean; user_agent: string | null; ip_address: string | null; created_at: string; last_seen_at: string; expires_at: string }>;
  plans: Plan[];
  billing: { provider: string; production_ready: boolean; checkout_available: boolean; notice: string | null };
};

export class AccountActionError extends Error {}
export async function customerAccountFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const cookieStore = await cookies();
  const session = cookieStore.get("aperture_session");
  if (!session) redirect("/login");
  const response = await fetch(`${process.env.API_ORIGIN ?? "http://localhost:8000"}${path}`, {
    ...init, cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      Origin: process.env.WEB_ORIGIN ?? "http://localhost:3000",
      cookie: `${session.name}=${session.value}`,
      ...(await forwardedGeoHeaders()),
      ...init?.headers,
    },
  });
  if (response.status === 401) redirect("/login?error=session-expired");
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new AccountActionError(body?.detail ?? `Account request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
