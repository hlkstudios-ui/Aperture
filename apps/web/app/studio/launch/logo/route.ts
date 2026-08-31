import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { requireAdminSession } from "@/app/lib/admin-session";
import { studioEdgeHeaders } from "@/app/lib/studio-edge";

export const dynamic = "force-dynamic";

export async function GET() {
  await requireAdminSession();
  const cookieStore = await cookies();
  const session = cookieStore.get("aperture_admin_session");
  if (!session) return new NextResponse(null, { status: 401 });
  const response = await fetch(`${process.env.API_ORIGIN ?? "http://localhost:8000"}/admin/site/brand/logo`, {
    cache: "no-store",
    headers: {
      cookie: `${session.name}=${session.value}`,
      ...studioEdgeHeaders(),
    },
  });
  if (!response.ok) return new NextResponse(null, { status: response.status === 404 ? 404 : 502 });
  return new NextResponse(response.body, {
    headers: {
      "Cache-Control": "private, no-store",
      "Content-Type": response.headers.get("content-type") ?? "application/octet-stream",
      "Content-Disposition": "inline",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
