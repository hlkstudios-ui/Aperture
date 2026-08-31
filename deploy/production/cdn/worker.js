const encoder = new TextEncoder();
const DOMAIN_KEY_PREFIX = "hostname:";
const INACTIVE_DOMAIN_STATUSES = new Set(["pending", "suspended", "deleted"]);
const REQUIRED_ENVIRONMENT = [
  "CDN_SIGNING_SECRET",
  "CDN_ORIGIN_SECRET",
  "ORIGIN_API",
  "WEB_ORIGIN",
];

function hasRequiredEnvironment(env) {
  return Boolean(env) && REQUIRED_ENVIRONMENT.every(
    (key) => typeof env[key] === "string" && env[key].trim().length > 0,
  );
}

function misconfiguredResponse() {
  return new Response("CDN edge is misconfigured", {
    status: 503,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "text/plain; charset=UTF-8",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

function normalizeHostname(value) {
  if (typeof value !== "string") return null;
  let hostname = value.trim().toLowerCase();
  if (hostname.endsWith(".")) hostname = hostname.slice(0, -1);
  if (!hostname || hostname.length > 253 || hostname.includes(":")) return null;
  const labels = hostname.split(".");
  if (
    labels.length < 2
    || labels.some(
      (label) => !label
        || label.length > 63
        || !/^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(label),
    )
  ) {
    return null;
  }
  return hostname;
}

function customDomainsEnabled(env) {
  const value = env?.CUSTOM_DOMAINS_ENABLED;
  if (value === undefined || value === "" || value === "false") return false;
  if (value === "true") return true;
  throw new TypeError("CUSTOM_DOMAINS_ENABLED must be true or false");
}

function configuredOrigin(value) {
  try {
    const origin = new URL(value);
    if (
      origin.protocol !== "https:"
      || origin.username
      || origin.password
      || origin.port
      || origin.pathname !== "/"
      || origin.search
      || origin.hash
      || !normalizeHostname(origin.hostname)
    ) {
      return null;
    }
    return origin;
  } catch {
    return null;
  }
}

async function customDomainStatus(hostname, env) {
  if (!env?.SITE_DOMAINS || typeof env.SITE_DOMAINS.get !== "function") {
    throw new TypeError("SITE_DOMAINS is not bound");
  }
  const record = await env.SITE_DOMAINS.get(`${DOMAIN_KEY_PREFIX}${hostname}`, { type: "json" });
  if (record === null) return "missing";
  if (!record || typeof record !== "object" || Array.isArray(record)) {
    throw new TypeError("SITE_DOMAINS record must be an object");
  }
  if (record.hostname !== undefined && normalizeHostname(record.hostname) !== hostname) {
    throw new TypeError("SITE_DOMAINS hostname does not match its key");
  }
  if (record.status === "active") return "active";
  if (INACTIVE_DOMAIN_STATUSES.has(record.status)) return "inactive";
  throw new TypeError("SITE_DOMAINS record has an invalid status");
}

async function admitRequestOrigin(request, env, canonicalOrigin) {
  const supplied = request.headers.get("Origin");
  if (supplied === null) return { outcome: "absent", origin: null };
  const origin = configuredOrigin(supplied);
  if (!origin) return { outcome: "denied", origin: null };
  if (origin.origin === canonicalOrigin.origin) {
    return { outcome: "active", origin: origin.origin };
  }
  if (!customDomainsEnabled(env)) return { outcome: "denied", origin: null };
  const hostname = normalizeHostname(origin.hostname);
  const status = await customDomainStatus(hostname, env);
  return status === "active"
    ? { outcome: "active", origin: origin.origin }
    : { outcome: "denied", origin: null };
}

function base64url(bytes) {
  let value = "";
  for (const byte of bytes) value += String.fromCharCode(byte);
  return btoa(value).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

export async function signature(secret, source, expires, session, country = "GLOBAL") {
  const key = await crypto.subtle.importKey(
    "raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"],
  );
  return base64url(new Uint8Array(await crypto.subtle.sign(
    "HMAC", key, encoder.encode(`${source}:${expires}:${session}:${country}`),
  )));
}

async function validSignature(secret, source, expires, session, country, supplied) {
  try {
    const padded = supplied.replaceAll("-", "+").replaceAll("_", "/")
      + "=".repeat((4 - supplied.length % 4) % 4);
    const raw = Uint8Array.from(atob(padded), (character) => character.charCodeAt(0));
    const key = await crypto.subtle.importKey(
      "raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["verify"],
    );
    return crypto.subtle.verify(
      "HMAC", key, raw, encoder.encode(`${source}:${expires}:${session}:${country}`),
    );
  } catch {
    return false;
  }
}

function response(body, status, origin) {
  const headers = new Headers({
    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
    "Access-Control-Allow-Headers": "Range",
    "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges",
    "Cache-Control": "no-store",
    "Vary": "Origin",
    "X-Content-Type-Options": "nosniff",
  });
  if (origin) headers.set("Access-Control-Allow-Origin", origin);
  return new Response(body, { status, headers });
}

export default {
  async fetch(request, env, context) {
    if (!hasRequiredEnvironment(env)) return misconfiguredResponse();
    const canonicalOrigin = configuredOrigin(env.WEB_ORIGIN);
    if (!canonicalOrigin) return misconfiguredResponse();
    let originAdmission;
    try {
      originAdmission = await admitRequestOrigin(request, env, canonicalOrigin);
    } catch {
      return response("Domain registry unavailable", 503, null);
    }
    if (originAdmission.outcome === "denied") return response("Forbidden", 403, null);
    if (request.method === "OPTIONS") {
      return originAdmission.outcome === "active"
        ? response(null, 204, originAdmission.origin)
        : response("Forbidden", 403, null);
    }
    const allowedOrigin = originAdmission.origin;
    if (!["GET", "HEAD"].includes(request.method)) return response("Not found", 404, allowedOrigin);
    const url = new URL(request.url);
    const parts = url.pathname.split("/").filter(Boolean);
    if (parts.length < 7 || parts[0] !== "media") return response("Not found", 404, allowedOrigin);
    const [, source, expiresText, session, country, supplied, ...objectParts] = parts;
    const expires = Number(expiresText);
    const now = Math.floor(Date.now() / 1000);
    const tokenTtl = Number(env.TOKEN_TTL_SECONDS);
    if (!Number.isSafeInteger(tokenTtl) || tokenTtl < 60 || tokenTtl > 900) {
      return response("Misconfigured", 503, allowedOrigin);
    }
    if (!Number.isSafeInteger(expires) || expires < now || expires > now + tokenTtl) {
      return response("Expired", 403, allowedOrigin);
    }
    if (!/^(GLOBAL|[A-Z]{2})$/.test(country)) return response("Forbidden", 403, allowedOrigin);
    if (!await validSignature(env.CDN_SIGNING_SECRET, source, expires, session, country, supplied)) {
      return response("Forbidden", 403, allowedOrigin);
    }
    const objectPath = objectParts.map(encodeURIComponent).join("/");
    const originUrl = `${env.ORIGIN_API.replace(/\/$/, "")}/edge-media/${source}/${expires}/${session}/${country}/${supplied}/${objectPath}`;
    const headers = new Headers({ "X-Aperture-Origin-Secret": env.CDN_ORIGIN_SECRET });
    const range = request.headers.get("Range");
    if (range) headers.set("Range", range);
    const cacheUrl = new URL(request.url);
    cacheUrl.pathname = `/cache/${source}/${country}/${objectPath}`;
    cacheUrl.search = "";
    const cacheKey = new Request(cacheUrl, { method: request.method });
    let originResponse = !range && request.method === "GET"
      ? await caches.default.match(cacheKey)
      : null;
    if (!originResponse) {
      originResponse = await fetch(originUrl, { method: request.method, headers });
      if (originResponse.ok && !range && request.method === "GET") {
        context.waitUntil(caches.default.put(cacheKey, originResponse.clone()));
      }
    }
    const outputHeaders = new Headers(originResponse.headers);
    outputHeaders.delete("Access-Control-Allow-Origin");
    if (allowedOrigin) outputHeaders.set("Access-Control-Allow-Origin", allowedOrigin);
    outputHeaders.set("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS");
    outputHeaders.set("Access-Control-Allow-Headers", "Range");
    outputHeaders.set("Access-Control-Expose-Headers", "Content-Length, Content-Range, Accept-Ranges");
    outputHeaders.set("Vary", "Origin");
    outputHeaders.delete("Set-Cookie");
    return new Response(originResponse.body, { status: originResponse.status, headers: outputHeaders });
  },
};
