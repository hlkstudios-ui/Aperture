import type { NextRequest } from "next/server";

import { isBrowserApiPrefix } from "@/app/lib/api-gateway-policy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type GatewayContext = {
  params: Promise<{ path?: string[] }>;
};

type StreamingRequestInit = RequestInit & {
  duplex?: "half";
};

const PRIVATE_CACHE_CONTROL = "private, no-store, max-age=0, must-revalidate";
const NULL_BODY_STATUSES = new Set([101, 204, 205, 304]);
const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "proxy-connection",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

const PUBLIC_HOST = /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?::\d{1,5})?$/i;

function connectionHeaderNames(headers: Headers): Set<string> {
  return new Set(
    (headers.get("connection") ?? "")
      .split(",")
      .map((value) => value.trim().toLowerCase())
      .filter(Boolean),
  );
}

function privateHeaders(headers: Headers = new Headers()): Headers {
  headers.set("Cache-Control", PRIVATE_CACHE_CONTROL);
  headers.set("Pragma", "no-cache");
  headers.set("Expires", "0");

  const vary = (headers.get("Vary") ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter((value) => value && value !== "*" && value.toLowerCase() !== "cookie");
  headers.set("Vary", [...vary, "Cookie"].join(", "));
  return headers;
}

function privateJson(detail: string, status: number): Response {
  return Response.json({ detail }, { status, headers: privateHeaders() });
}

function upstreamUrl(request: NextRequest, path: string[] | undefined): URL | null {
  if (!path?.length || !isBrowserApiPrefix(path[0])) return null;
  if (
    path.some(
      (segment) =>
        segment.length === 0 ||
        segment === "." ||
        segment === ".." ||
        segment.includes("/") ||
        segment.includes("\\") ||
        segment.includes("\0"),
    )
  ) {
    return null;
  }

  const configured = process.env.API_ORIGIN ?? "http://localhost:8000";
  const target = new URL(configured);
  if (
    !["http:", "https:"].includes(target.protocol) ||
    target.username ||
    target.password ||
    target.search ||
    target.hash
  ) {
    throw new TypeError("API_ORIGIN must be an HTTP(S) origin or base URL");
  }

  const basePath = target.pathname.replace(/\/+$/, "");
  target.pathname = `${basePath}/${path.map((segment) => encodeURIComponent(segment)).join("/")}`;
  target.search = request.nextUrl.search;
  return target;
}

function upstreamRequestHeaders(request: NextRequest): Headers {
  const headers = new Headers();
  const connectionNames = connectionHeaderNames(request.headers);
  request.headers.forEach((value, key) => {
    const name = key.toLowerCase();
    if (
      HOP_BY_HOP_HEADERS.has(name) ||
      connectionNames.has(name) ||
      name === "host" ||
      name === "accept-encoding" ||
      name === "x-aperture-edge-secret" ||
      name === "x-aperture-public-origin" ||
      name === "x-aperture-studio-edge"
    ) {
      return;
    }
    headers.append(key, value);
  });
  // Fetch transparently decompresses upstream responses. Request identity
  // encoding so media ranges and response metadata cannot become mismatched.
  headers.set("Accept-Encoding", "identity");
  const edgeSecret = process.env.CUSTOM_DOMAIN_EDGE_SECRET;
  if (edgeSecret) {
    headers.set("X-Aperture-Public-Origin", requestPublicOrigin(request));
    headers.set("X-Aperture-Edge-Secret", edgeSecret);
  }
  return headers;
}

function requestPublicOrigin(request: NextRequest): string {
  // In production this header is replaced by the trusted edge before the
  // request reaches the protected origin. It survives the origin-host rewrite
  // so links and CSRF checks continue to use the customer's public hostname.
  const assertedHost = request.headers.get("x-aperture-public-host")?.trim();
  if (assertedHost && assertedHost.length <= 259 && PUBLIC_HOST.test(assertedHost)) {
    const forwardedProtocol = request.headers
      .get("x-forwarded-proto")
      ?.split(",", 1)[0]
      ?.trim()
      .toLowerCase();
    const protocol = forwardedProtocol === "http" || forwardedProtocol === "https"
      ? forwardedProtocol
      : request.nextUrl.protocol.replace(":", "");
    try {
      return new URL(`${protocol}://${assertedHost}`).origin;
    } catch {
      // Fall back to Next's parsed request origin below.
    }
  }
  return request.nextUrl.origin;
}

function downstreamResponseHeaders(response: Response): Headers {
  const headers = new Headers();
  const connectionNames = connectionHeaderNames(response.headers);
  response.headers.forEach((value, key) => {
    const name = key.toLowerCase();
    if (
      HOP_BY_HOP_HEADERS.has(name) ||
      connectionNames.has(name) ||
      name === "set-cookie" ||
      name === "content-encoding" ||
      name === "content-length" ||
      name === "server"
    ) {
      return;
    }
    headers.append(key, value);
  });

  for (const cookie of response.headers.getSetCookie()) {
    headers.append("Set-Cookie", cookie);
  }
  return privateHeaders(headers);
}

async function gateway(request: NextRequest, context: GatewayContext): Promise<Response> {
  let target: URL | null;
  try {
    target = upstreamUrl(request, (await context.params).path);
  } catch {
    return privateJson("Gateway unavailable", 502);
  }
  if (!target) return privateJson("Not found", 404);

  const hasBody = request.method !== "GET" && request.method !== "HEAD" && request.body !== null;
  const init: StreamingRequestInit = {
    method: request.method,
    headers: upstreamRequestHeaders(request),
    body: hasBody ? request.body : undefined,
    cache: "no-store",
    redirect: "manual",
    signal: request.signal,
  };
  if (hasBody) init.duplex = "half";

  try {
    const upstream = await fetch(target, init);
    const body = request.method === "HEAD" || NULL_BODY_STATUSES.has(upstream.status)
      ? null
      : upstream.body;
    return new Response(body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: downstreamResponseHeaders(upstream),
    });
  } catch {
    return privateJson("Gateway unavailable", 502);
  }
}

export function GET(request: NextRequest, context: GatewayContext): Promise<Response> {
  return gateway(request, context);
}

export function HEAD(request: NextRequest, context: GatewayContext): Promise<Response> {
  return gateway(request, context);
}

export function POST(request: NextRequest, context: GatewayContext): Promise<Response> {
  return gateway(request, context);
}

export function PUT(request: NextRequest, context: GatewayContext): Promise<Response> {
  return gateway(request, context);
}

export function PATCH(request: NextRequest, context: GatewayContext): Promise<Response> {
  return gateway(request, context);
}

export function DELETE(request: NextRequest, context: GatewayContext): Promise<Response> {
  return gateway(request, context);
}

export function OPTIONS(request: NextRequest, context: GatewayContext): Promise<Response> {
  return gateway(request, context);
}
