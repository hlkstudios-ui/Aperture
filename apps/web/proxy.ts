import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { featureFlags } from "@/app/lib/feature-flags";
import { approvedPolicy } from "@/app/lib/policies";
import { STUDIO_EDGE_HEADER, validStudioEdgeValue } from "@/app/lib/studio-edge";

export function proxy(request: NextRequest) {
  const path = request.nextUrl.pathname;
  const policySlug = path.startsWith("/policies/") ? path.slice("/policies/".length) : null;
  const disabled =
    (!featureFlags.community && (path === "/community" || path.startsWith("/community/") || path === "/clubs" || path.startsWith("/clubs/"))) ||
    (!featureFlags.watchParties && path.startsWith("/clubs/parties/")) ||
    (!featureFlags.experimentalRecommendations && (path === "/discover" || path === "/prescription")) ||
    (policySlug !== null && (!policySlug || !approvedPolicy(policySlug)));
  if (disabled) {
    return NextResponse.rewrite(new URL("/_not-found", request.url), { status: 404 });
  }
  if (path === "/studio" || path.startsWith("/studio/")) {
    if (!validStudioEdgeValue(request.headers.get(STUDIO_EDGE_HEADER))) {
      return NextResponse.rewrite(new URL("/_not-found", request.url), { status: 404 });
    }
    if (path === "/studio/login") return NextResponse.next();
    if (request.cookies.has("aperture_admin_session")) return NextResponse.next();
    const loginUrl = new URL("/studio/login", request.url);
    loginUrl.searchParams.set("next", request.nextUrl.pathname);
    return NextResponse.redirect(loginUrl);
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/studio/:path*",
    "/community/:path*",
    "/clubs/:path*",
    "/discover",
    "/prescription",
    "/policies/:path*",
  ],
};
