const encoder = new TextEncoder();

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
    if (!env.ORIGIN_WEB || !env.GEO_ASSERTION_SECRET || !env.ORIGIN_EDGE_SECRET) {
      return new Response("Geo edge is misconfigured", { status: 503 });
    }
    const country = request.cf?.country?.toUpperCase();
    if (!country || !/^[A-Z]{2}$/.test(country)) {
      return new Response("Viewer region is unavailable", { status: 403 });
    }
    const timestamp = Math.floor(Date.now() / 1000);
    const headers = new Headers(request.headers);
    headers.delete("X-Aperture-Country");
    headers.delete("X-Aperture-Geo-Timestamp");
    headers.delete("X-Aperture-Geo-Signature");
    headers.delete("X-Aperture-Origin-Secret");
    headers.set("X-Aperture-Country", country);
    headers.set("X-Aperture-Geo-Timestamp", String(timestamp));
    headers.set(
      "X-Aperture-Geo-Signature",
      await geoSignature(env.GEO_ASSERTION_SECRET, country, timestamp),
    );
    headers.set("X-Forwarded-Host", new URL(request.url).host);
    headers.set("X-Aperture-Origin-Secret", env.ORIGIN_EDGE_SECRET);

    const upstream = new URL(request.url);
    const origin = new URL(env.ORIGIN_WEB);
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
