const encoder = new TextEncoder();

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
  return new Response(body, {
    status,
    headers: {
      "Access-Control-Allow-Origin": origin,
      "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
      "Access-Control-Allow-Headers": "Range",
      "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges",
      "Vary": "Origin",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

export default {
  async fetch(request, env, context) {
    if (request.method === "OPTIONS") return response(null, 204, env.WEB_ORIGIN);
    if (!['GET', 'HEAD'].includes(request.method)) return response("Not found", 404, env.WEB_ORIGIN);
    const url = new URL(request.url);
    const parts = url.pathname.split("/").filter(Boolean);
    if (parts.length < 7 || parts[0] !== "media") return response("Not found", 404, env.WEB_ORIGIN);
    const [, source, expiresText, session, country, supplied, ...objectParts] = parts;
    const expires = Number(expiresText);
    const now = Math.floor(Date.now() / 1000);
    const tokenTtl = Number(env.TOKEN_TTL_SECONDS);
    if (!Number.isSafeInteger(tokenTtl) || tokenTtl < 60 || tokenTtl > 900) {
      return response("Misconfigured", 503, env.WEB_ORIGIN);
    }
    if (!Number.isSafeInteger(expires) || expires < now || expires > now + tokenTtl) {
      return response("Expired", 403, env.WEB_ORIGIN);
    }
    if (!/^(GLOBAL|[A-Z]{2})$/.test(country)) return response("Forbidden", 403, env.WEB_ORIGIN);
    if (!await validSignature(env.CDN_SIGNING_SECRET, source, expires, session, country, supplied)) {
      return response("Forbidden", 403, env.WEB_ORIGIN);
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
    outputHeaders.set("Access-Control-Allow-Origin", env.WEB_ORIGIN);
    outputHeaders.set("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS");
    outputHeaders.set("Access-Control-Allow-Headers", "Range");
    outputHeaders.set("Access-Control-Expose-Headers", "Content-Length, Content-Range, Accept-Ranges");
    outputHeaders.set("Vary", "Origin");
    outputHeaders.delete("Set-Cookie");
    return new Response(originResponse.body, { status: originResponse.status, headers: outputHeaders });
  },
};
