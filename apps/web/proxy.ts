import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { featureFlags } from "@/app/lib/feature-flags";
import { approvedPolicy } from "@/app/lib/policies";
import {
  studioDevelopmentAccessEnabled,
  studioDevelopmentAccessPath,
} from "@/app/lib/studio-development-access";
import { STUDIO_EDGE_HEADER, validStudioEdgeValue } from "@/app/lib/studio-edge";

const PRIVATE_STUDIO_HEADERS = {
  "Cache-Control": "private, no-store, max-age=0, must-revalidate",
  "X-Robots-Tag": "noindex, nofollow, noarchive, nosnippet",
} as const;

function privateStudioResponse(response: NextResponse): NextResponse {
  for (const [key, value] of Object.entries(PRIVATE_STUDIO_HEADERS)) {
    response.headers.set(key, value);
  }
  return response;
}

function hiddenStudioResponse(): NextResponse {
  return privateStudioResponse(new NextResponse(null, { status: 404 }));
}

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
  const studioApi = path === "/api/gateway/admin" || path.startsWith("/api/gateway/admin/");
  if (path === "/studio" || path.startsWith("/studio/") || studioApi) {
    if (!validStudioEdgeValue(request.headers.get(STUDIO_EDGE_HEADER))) {
      return hiddenStudioResponse();
    }
    if (studioApi) return privateStudioResponse(NextResponse.next());
    // The route handler independently enforces development mode, localhost,
    // same-site navigation, and the owner-session feature flag.
    if (path === "/studio/dev-access") return privateStudioResponse(NextResponse.next());
    if (path === "/studio/login") return privateStudioResponse(NextResponse.next());
    if (request.cookies.has("aperture_admin_session")) {
      return privateStudioResponse(NextResponse.next());
    }
    if (studioDevelopmentAccessEnabled()) {
      const bootstrapUrl = new URL(
        studioDevelopmentAccessPath(`${request.nextUrl.pathname}${request.nextUrl.search}`),
        request.url,
      );
      return privateStudioResponse(NextResponse.redirect(bootstrapUrl));
    }
    const loginUrl = new URL("/studio/login", request.url);
    loginUrl.searchParams.set("next", `${request.nextUrl.pathname}${request.nextUrl.search}`);
    return privateStudioResponse(NextResponse.redirect(loginUrl));
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    // Keep owner-only route names out of the browser-visible matcher manifest.
    // Proxy cheaply passes through unrelated paths after applying the checks above.
    "/((?!_next/static|_next/image|favicon.ico|icon.svg).*)",
  ],
};
