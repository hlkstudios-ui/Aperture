import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { studioEdgeHeaders } from "@/app/lib/studio-edge";

type AdminSession = { id: string; email: string; mfa_enabled: boolean };

export async function requireAdminSession(): Promise<AdminSession> {
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get("aperture_admin_session");
  if (!sessionCookie) redirect("/studio/login");

  const apiOrigin = process.env.API_ORIGIN ?? "http://localhost:8000";
  let response: Response;
  try {
    response = await fetch(`${apiOrigin}/admin/auth/me`, {
      headers: { cookie: `${sessionCookie.name}=${sessionCookie.value}`, ...studioEdgeHeaders() },
      cache: "no-store",
    });
  } catch {
    redirect("/studio/login?error=service-unavailable");
  }
  if (!response.ok) redirect("/studio/login?error=session-expired");
  return response.json() as Promise<AdminSession>;
}
