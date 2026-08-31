import { NextRequest, NextResponse } from "next/server";
import {
  safeStudioDestination,
  studioDevelopmentAccessEnabled,
} from "@/app/lib/studio-development-access";
import { studioEdgeHeaders } from "@/app/lib/studio-edge";

const privateHeaders = {
  "Cache-Control": "private, no-store, max-age=0",
  Vary: "Cookie",
};

function localRequestOrigin(request: NextRequest): string | null {
  const host = request.headers.get("host");
  if (!host || request.headers.get("sec-fetch-site") === "cross-site") return null;
  let hostname: string;
  try {
    hostname = new URL(`http://${host}`).hostname;
  } catch {
    return null;
  }
  const localHostname =
    hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]" || hostname === "::1";
  return localHostname ? `${request.nextUrl.protocol}//${host}` : null;
}

function manualLogin(origin: string, error: string): NextResponse {
  const login = new URL("/studio/login", origin);
  login.searchParams.set("manual", "1");
  login.searchParams.set("error", error);
  return NextResponse.redirect(login, { headers: privateHeaders });
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const localOrigin = localRequestOrigin(request);
  if (!studioDevelopmentAccessEnabled() || !localOrigin) {
    return new NextResponse(null, { status: 404, headers: privateHeaders });
  }

  const destination = safeStudioDestination(request.nextUrl.searchParams.get("next"));
  const apiOrigin = process.env.API_ORIGIN ?? "http://localhost:8000";
  const currentSession = request.cookies.get("aperture_admin_session");
  if (currentSession) {
    try {
      const currentAdmin = await fetch(`${apiOrigin}/admin/auth/me`, {
        headers: {
          cookie: `${currentSession.name}=${currentSession.value}`,
          ...studioEdgeHeaders(),
        },
        cache: "no-store",
      });
      if (currentAdmin.ok) {
        return NextResponse.redirect(new URL(destination, localOrigin), {
          headers: privateHeaders,
        });
      }
    } catch {
      // A stale or unverifiable local session is replaced below.
    }
  }

  let response: Response;
  try {
    response = await fetch(
      `${apiOrigin}/admin/auth/development-session`,
      {
        method: "POST",
        headers: {
          Origin: process.env.WEB_ORIGIN ?? "http://localhost:3000",
          ...studioEdgeHeaders(),
        },
        cache: "no-store",
      },
    );
  } catch {
    return manualLogin(localOrigin, "development-access-unavailable");
  }

  if (!response.ok) return manualLogin(localOrigin, "development-access-unavailable");
  const sessionCookie = response.headers.get("set-cookie");
  if (!sessionCookie) return manualLogin(localOrigin, "development-session-missing");

  const result = NextResponse.redirect(new URL(destination, localOrigin), {
    headers: privateHeaders,
  });
  result.headers.set("set-cookie", sessionCookie);
  return result;
}
