export const API_GATEWAY_PREFIX = "/api/gateway";

/**
 * Maps an upstream API path onto the browser-safe, same-origin gateway.
 * Only absolute-path API routes are accepted so callers cannot turn the
 * helper into an open redirect or an arbitrary-origin fetch.
 */
export function apiGatewayPath(path: string): string {
  if (!path.startsWith("/") || path.startsWith("//")) {
    throw new TypeError("API gateway paths must begin with one slash");
  }
  return `${API_GATEWAY_PREFIX}${path}`;
}

const MANAGED_MEDIA_PATH = /^\/playback\/sources\/[^/]+\/media(?:\/|$)/;

/**
 * Playback configuration is produced server-side, but managed-media URLs in
 * that payload are consumed by the browser. Convert only API-owned media
 * routes; licensed third-party/CDN URLs intentionally remain untouched.
 */
export function browserPlaybackUrl(value: string, apiOrigin: string): string {
  if (value.startsWith("/") && !value.startsWith("//")) {
    return MANAGED_MEDIA_PATH.test(new URL(value, "https://gateway.invalid").pathname)
      ? apiGatewayPath(value)
      : value;
  }

  try {
    const parsed = new URL(value);
    const allowedOrigin = new URL(apiOrigin).origin;
    return parsed.origin === allowedOrigin && MANAGED_MEDIA_PATH.test(parsed.pathname)
      ? apiGatewayPath(`${parsed.pathname}${parsed.search}${parsed.hash}`)
      : value;
  } catch {
    return value;
  }
}

export function isGatewayUrl(value: string, base: string): boolean {
  try {
    const parsed = new URL(value, base);
    return parsed.origin === new URL(base).origin
      && (parsed.pathname === API_GATEWAY_PREFIX || parsed.pathname.startsWith(`${API_GATEWAY_PREFIX}/`));
  } catch {
    return false;
  }
}
