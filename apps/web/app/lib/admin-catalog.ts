import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { requireAdminSession } from "@/app/lib/admin-session";
import { studioEdgeHeaders } from "@/app/lib/studio-edge";

const apiOrigin = process.env.API_ORIGIN ?? "http://localhost:8000";

export class CatalogActionError extends Error {
  constructor(public detail: string) {
    super(detail);
  }
}

export async function adminCatalogFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  await requireAdminSession();
  const cookieStore = await cookies();
  const session = cookieStore.get("aperture_admin_session");
  if (!session) redirect("/studio/login");
  const response = await fetch(`${apiOrigin}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      Origin: process.env.WEB_ORIGIN ?? "http://localhost:3000",
      cookie: `${session.name}=${session.value}`,
      ...studioEdgeHeaders(),
      ...init?.headers,
    },
  });
  if (response.status === 401) redirect("/studio/login?error=session-expired");
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: string | Array<{ msg: string }>;
    } | null;
    const detail = Array.isArray(body?.detail)
      ? body.detail.map((item) => item.msg).join(". ")
      : body?.detail;
    throw new CatalogActionError(
      detail ?? `Catalog request failed (${response.status})`,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
