"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { studioEdgeHeaders } from "@/app/lib/studio-edge";

export async function signOutAdmin() {
  const cookieStore = await cookies();
  const session = cookieStore.get("aperture_admin_session");
  if (session) {
    await fetch(`${process.env.API_ORIGIN ?? "http://localhost:8000"}/admin/auth/logout`, {
      method: "POST",
      headers: {
        cookie: `${session.name}=${session.value}`,
        origin: process.env.WEB_ORIGIN ?? "http://localhost:3000",
        ...studioEdgeHeaders(),
      },
      cache: "no-store",
    }).catch(() => null);
    cookieStore.delete("aperture_admin_session");
  }
  redirect("/studio/login?signed-out=1");
}
