import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const privateHeaders = {
  "Cache-Control": "private, no-store, max-age=0",
  Vary: "Cookie",
};

export async function GET() {
  const session = (await cookies()).get("aperture_session");
  if (!session) return new NextResponse(null, { status: 204, headers: privateHeaders });
  try {
    const response = await fetch(`${process.env.API_ORIGIN ?? "http://localhost:8000"}/auth/me`, {
      headers: { cookie: `${session.name}=${session.value}` },
      cache: "no-store",
    });
    if (!response.ok) return new NextResponse(null, { status: 204, headers: privateHeaders });
    return NextResponse.json(await response.json(), { headers: privateHeaders });
  } catch {
    return new NextResponse(null, { status: 204, headers: privateHeaders });
  }
}
