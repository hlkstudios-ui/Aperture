import { headers } from "next/headers";

const PUBLIC_HOST = /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?::\d{1,5})?$/i;

/**
 * Resolve the storefront origin retained by the trusted edge.
 *
 * The production Worker removes a browser-supplied public-host assertion and
 * writes the verified hostname before forwarding to the protected origin. The
 * configured canonical origin remains the safe fallback for builds, tests, and
 * installations that do not use a custom domain.
 */
export async function currentStorefrontOrigin(): Promise<string> {
  const fallback = new URL(process.env.WEB_ORIGIN ?? "http://localhost:3000").origin;
  try {
    const incoming = await headers();
    const assertedHost = incoming.get("x-aperture-public-host")?.trim();
    const forwardedHost = incoming.get("x-forwarded-host")?.split(",", 1)[0]?.trim();
    const host = assertedHost && PUBLIC_HOST.test(assertedHost)
      ? assertedHost
      : forwardedHost && PUBLIC_HOST.test(forwardedHost)
        ? forwardedHost
        : incoming.get("host")?.trim();
    if (!host || host.length > 259 || !PUBLIC_HOST.test(host)) return fallback;

    const forwardedProtocol = incoming
      .get("x-forwarded-proto")
      ?.split(",", 1)[0]
      ?.trim()
      .toLowerCase();
    const protocol = forwardedProtocol === "http" || forwardedProtocol === "https"
      ? forwardedProtocol
      : new URL(fallback).protocol.replace(":", "");
    return new URL(`${protocol}://${host}`).origin;
  } catch {
    return fallback;
  }
}

/**
 * Resolve the owner-selected indexable front door without making aliases redirect.
 * If the control plane cannot answer, the permanent platform-hosted origin is the
 * conservative fallback.
 */
export async function primaryStorefrontOrigin(): Promise<string> {
  const fallback = new URL(process.env.WEB_ORIGIN ?? "http://localhost:3000").origin;
  const apiOrigin = (process.env.API_ORIGIN ?? "http://localhost:8000").replace(/\/+$/, "");
  try {
    const response = await fetch(`${apiOrigin}/site/domain`, {
      next: { revalidate: 60, tags: ["site-domain"] },
    });
    if (!response.ok) return fallback;
    const payload: unknown = await response.json();
    if (!payload || typeof payload !== "object") return fallback;
    const value = (payload as { primary_origin?: unknown }).primary_origin;
    if (typeof value !== "string") return fallback;
    const parsed = new URL(value);
    const developmentHttp = process.env.NODE_ENV !== "production" && parsed.protocol === "http:";
    if (
      (parsed.protocol !== "https:" && !developmentHttp)
      || parsed.username
      || parsed.password
      || parsed.pathname !== "/"
      || parsed.search
      || parsed.hash
    ) {
      return fallback;
    }
    return parsed.origin;
  } catch {
    return fallback;
  }
}
