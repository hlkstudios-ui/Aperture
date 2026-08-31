const encoder = new TextEncoder();
const PUBLIC_HOST_HEADER = "X-Aperture-Public-Host";
const PUBLIC_ORIGIN_HEADER = "X-Aperture-Public-Origin";
const EDGE_SECRET_HEADER = "X-Aperture-Edge-Secret";
const DOMAIN_KEY_PREFIX = "hostname:";
const INACTIVE_DOMAIN_STATUSES = new Set(["pending", "suspended", "deleted"]);

// Cloudflare normally supplies ISO 3166-1 alpha-2 country codes, but can also
// supply special values such as XX (unknown) or T1 (Tor). An allowlist keeps
// every special or otherwise unassigned code out of signed geo assertions.
const ISO_COUNTRY_CODES = new Set(`
AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ
BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ
CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ
DE DJ DK DM DO DZ
EC EE EG EH ER ES ET
FI FJ FK FM FO FR
GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY
HK HM HN HR HT HU
ID IE IL IM IN IO IQ IR IS IT
JE JM JO JP
KE KG KH KI KM KN KP KR KW KY KZ
LA LB LC LI LK LR LS LT LU LV LY
MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ
NA NC NE NF NG NI NL NO NP NR NU NZ
OM
PA PE PF PG PH PK PL PM PN PR PS PT PW PY
QA
RE RO RS RU RW
SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ
TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ
UA UG UM US UY UZ
VA VC VE VG VI VN VU
WF WS
YE YT
ZA ZM ZW
`.trim().split(/\s+/));

function trustedCountry(value) {
  if (typeof value !== "string") return null;
  const country = value.toUpperCase();
  return ISO_COUNTRY_CODES.has(country) ? country : null;
}

function edgeResponse(body, status) {
  return new Response(body, {
    status,
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
      || origin.pathname !== "/"
      || origin.search
      || origin.hash
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

async function admitPublicHost(request, env, canonicalHost) {
  const requestHost = normalizeHostname(new URL(request.url).hostname);
  if (!requestHost) return { outcome: "missing" };
  if (requestHost === canonicalHost) {
    return { outcome: "active", hostname: requestHost, custom: false };
  }
  if (!customDomainsEnabled(env)) return { outcome: "missing" };
  const status = await customDomainStatus(requestHost, env);
  return status === "active"
    ? { outcome: "active", hostname: requestHost, custom: true }
    : { outcome: "missing" };
}

function hex(bytes) {
  return [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function geoSignature(secret, country, timestamp) {
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return hex(
    new Uint8Array(
      await crypto.subtle.sign(
        "HMAC",
        key,
        encoder.encode(`${country}:${timestamp}`),
      ),
    ),
  );
}

export default {
  async fetch(request, env) {
    const canonicalHost = normalizeHostname(env?.CANONICAL_HOST);
    const origin = configuredOrigin(env?.ORIGIN_WEB);
    if (!canonicalHost || !origin || !env?.GEO_ASSERTION_SECRET || !env?.ORIGIN_EDGE_SECRET) {
      return edgeResponse("Geo edge is misconfigured", 503);
    }
    let admission;
    try {
      admission = await admitPublicHost(request, env, canonicalHost);
    } catch {
      return edgeResponse("Domain registry unavailable", 503);
    }
    if (admission.outcome !== "active") {
      return edgeResponse("Not found", 404);
    }
    const customDomainEdgeSecret = env?.CUSTOM_DOMAIN_EDGE_SECRET?.trim();
    if (admission.custom && !customDomainEdgeSecret) {
      return edgeResponse("Custom domain edge is misconfigured", 503);
    }
    const country = trustedCountry(request.cf?.country);
    if (!country) {
      return edgeResponse("Viewer region is unavailable", 403);
    }
    const timestamp = Math.floor(Date.now() / 1000);
    const headers = new Headers(request.headers);
    for (const name of [...headers.keys()]) {
      if (name.toLowerCase().startsWith("x-aperture-")) headers.delete(name);
    }
    headers.delete("X-Forwarded-Host");
    headers.set("X-Aperture-Country", country);
    headers.set("X-Aperture-Geo-Timestamp", String(timestamp));
    headers.set(
      "X-Aperture-Geo-Signature",
      await geoSignature(env.GEO_ASSERTION_SECRET, country, timestamp),
    );
    headers.set(PUBLIC_HOST_HEADER, admission.hostname);
    headers.set(PUBLIC_ORIGIN_HEADER, `https://${admission.hostname}`);
    headers.set("X-Forwarded-Host", admission.hostname);
    if (customDomainEdgeSecret) {
      headers.set(EDGE_SECRET_HEADER, customDomainEdgeSecret);
    }
    headers.set("X-Aperture-Origin-Secret", env.ORIGIN_EDGE_SECRET);

    const upstream = new URL(request.url);
    upstream.protocol = origin.protocol;
    upstream.host = origin.host;
    return fetch(
      new Request(upstream, {
        method: request.method,
        headers,
        body: request.body,
        redirect: "manual",
      }),
    );
  },
};
