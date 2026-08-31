import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import worker, { signature } from "./worker.js";

const env = {
  CDN_SIGNING_SECRET: "dummy-signing-secret-with-at-least-32-characters",
  CDN_ORIGIN_SECRET: "dummy-origin-secret-with-at-least-32-characters",
  ORIGIN_API: "https://watch.example.test/api",
  WEB_ORIGIN: "https://watch.example.test",
  TOKEN_TTL_SECONDS: "300",
  CUSTOM_DOMAINS_ENABLED: "false",
};

test("checked-in deployment config exposes no public preview endpoint", () => {
  const config = readFileSync(new URL("./wrangler.toml.example", import.meta.url), "utf8");
  assert.match(config, /^workers_dev = false$/m);
  assert.match(config, /^preview_urls = false$/m);
  assert.match(config, /^CUSTOM_DOMAINS_ENABLED = "false"$/m);
  assert.match(config, /binding = "SITE_DOMAINS"/);
});

async function requestPath(objectPath = "master.m3u8", country = "CA") {
  const source = "11111111-1111-4111-8111-111111111111";
  const session = "22222222-2222-4222-8222-222222222222";
  const expires = Math.floor(Date.now() / 1000) + 300;
  const grant = await signature(env.CDN_SIGNING_SECRET, source, expires, session, country);
  return `/media/${source}/${expires}/${session}/${country}/${grant}/${objectPath}`;
}

test("valid grants reach the secret origin and cache immutable objects", async () => {
  const stored = new Map();
  globalThis.caches = {
    default: {
      match: async (key) => stored.get(key.url),
      put: async (key, value) => stored.set(key.url, value),
    },
  };
  let originRequests = 0;
  globalThis.fetch = async (request, init) => {
    originRequests += 1;
    assert.equal(init.headers.get("X-Aperture-Origin-Secret"), env.CDN_ORIGIN_SECRET);
    assert.match(request, /\/edge-media\//);
    return new Response("#EXTM3U", {
      status: 200,
      headers: { "Content-Type": "application/vnd.apple.mpegurl" },
    });
  };
  const path = await requestPath();
  const context = { waitUntil: (promise) => promise };
  const first = await worker.fetch(new Request(`https://media.example.test${path}`, {
    headers: { Origin: env.WEB_ORIGIN },
  }), env, context);
  assert.equal(first.status, 200);
  assert.equal(first.headers.get("Access-Control-Allow-Origin"), env.WEB_ORIGIN);
  await new Promise((resolve) => setTimeout(resolve, 0));
  const second = await worker.fetch(new Request(`https://media.example.test${path}`, {
    headers: { Origin: env.WEB_ORIGIN },
  }), env, context);
  assert.equal(second.status, 200);
  assert.equal(originRequests, 1);
});

test("tampered and expired grants fail before cache or origin access", async () => {
  globalThis.caches = { default: { match: async () => { throw new Error("cache reached"); } } };
  globalThis.fetch = async () => { throw new Error("origin reached"); };
  const path = await requestPath();
  const pieces = path.split("/");
  pieces[6] = `${pieces[6][0] === "A" ? "B" : "A"}${pieces[6].slice(1)}`;
  const denied = await worker.fetch(
    new Request(`https://media.example.test${pieces.join("/")}`), env, { waitUntil() {} },
  );
  assert.equal(denied.status, 403);
  const changedRegion = path.replace("/CA/", "/US/");
  assert.equal((await worker.fetch(
    new Request(`https://media.example.test${changedRegion}`), env, { waitUntil() {} },
  )).status, 403);
  const expired = path.replace(/\/\d{10}\//, "/1000000000/");
  assert.equal((await worker.fetch(
    new Request(`https://media.example.test${expired}`), env, { waitUntil() {} },
  )).status, 403);
});

test("range requests bypass cache and preserve the byte range", async () => {
  globalThis.caches = {
    default: { match: async () => { throw new Error("range touched cache"); } },
  };
  globalThis.fetch = async (_request, init) => {
    assert.equal(init.headers.get("Range"), "bytes=2-5");
    return new Response("2345", {
      status: 206,
      headers: {
        "Content-Range": "bytes 2-5/10",
        "Accept-Ranges": "bytes",
        "Access-Control-Allow-Origin": "https://untrusted-origin-response.example",
      },
    });
  };
  const result = await worker.fetch(
    new Request(`https://media.example.test${await requestPath("360p/segment.ts")}`, {
      headers: { Range: "bytes=2-5" },
    }),
    env,
    { waitUntil() {} },
  );
  assert.equal(result.status, 206);
  assert.equal(result.headers.get("Content-Range"), "bytes 2-5/10");
  assert.equal(result.headers.get("Access-Control-Allow-Origin"), null);
});

test("canonical CORS remains available without a custom-domain registry", async () => {
  const result = await worker.fetch(
    new Request("https://media.example.test/", {
      method: "OPTIONS",
      headers: { Origin: env.WEB_ORIGIN },
    }),
    { ...env, CUSTOM_DOMAINS_ENABLED: "true", SITE_DOMAINS: undefined },
    { waitUntil() {} },
  );
  assert.equal(result.status, 204);
  assert.equal(result.headers.get("Access-Control-Allow-Origin"), env.WEB_ORIGIN);
});

test("only active custom origins in SITE_DOMAINS receive CORS", async () => {
  const records = new Map([
    ["hostname:active.customer.test", {
      hostname: "active.customer.test",
      status: "active",
    }],
    ["hostname:pending.customer.test", { status: "pending" }],
  ]);
  const customEnv = {
    ...env,
    CUSTOM_DOMAINS_ENABLED: "true",
    SITE_DOMAINS: { get: async (key) => records.get(key) ?? null },
  };

  const active = await worker.fetch(
    new Request("https://media.example.test/", {
      method: "OPTIONS",
      headers: { Origin: "https://active.customer.test" },
    }),
    customEnv,
    { waitUntil() {} },
  );
  assert.equal(active.status, 204);
  assert.equal(
    active.headers.get("Access-Control-Allow-Origin"),
    "https://active.customer.test",
  );

  for (const origin of [
    "https://pending.customer.test",
    "https://unknown.customer.test",
  ]) {
    const denied = await worker.fetch(
      new Request("https://media.example.test/", {
        method: "OPTIONS",
        headers: { Origin: origin },
      }),
      customEnv,
      { waitUntil() {} },
    );
    assert.equal(denied.status, 403);
    assert.equal(denied.headers.get("Access-Control-Allow-Origin"), null);
    assert.equal(denied.headers.get("Cache-Control"), "no-store");
  }
});

test("custom-origin CORS is disabled by default and invalid origins fail closed", async () => {
  for (const origin of [
    "https://customer.test",
    "http://watch.example.test",
    "null",
    "https://watch.example.test:8443",
  ]) {
    const result = await worker.fetch(
      new Request("https://media.example.test/", {
        method: "OPTIONS",
        headers: { Origin: origin },
      }),
      { ...env, CUSTOM_DOMAINS_ENABLED: undefined },
      { waitUntil() {} },
    );
    assert.equal(result.status, 403, origin);
    assert.equal(result.headers.get("Access-Control-Allow-Origin"), null);
  }

  const absent = await worker.fetch(
    new Request("https://media.example.test/", { method: "OPTIONS" }),
    env,
    { waitUntil() {} },
  );
  assert.equal(absent.status, 403);
});

test("enabled registry failures and malformed records return 503 before media work", async () => {
  const originalCaches = globalThis.caches;
  const originalFetch = globalThis.fetch;
  globalThis.caches = {
    default: { match: async () => { throw new Error("cache reached"); } },
  };
  globalThis.fetch = async () => { throw new Error("origin reached"); };
  try {
    for (const customEnvironment of [
      { CUSTOM_DOMAINS_ENABLED: "true", SITE_DOMAINS: undefined },
      {
        CUSTOM_DOMAINS_ENABLED: "true",
        SITE_DOMAINS: { get: async () => { throw new Error("KV unavailable"); } },
      },
      {
        CUSTOM_DOMAINS_ENABLED: "true",
        SITE_DOMAINS: { get: async () => ({ status: "unexpected" }) },
      },
      {
        CUSTOM_DOMAINS_ENABLED: "true",
        SITE_DOMAINS: {
          get: async () => ({ hostname: "other.customer.test", status: "active" }),
        },
      },
      { CUSTOM_DOMAINS_ENABLED: "invalid", SITE_DOMAINS: undefined },
    ]) {
      const result = await worker.fetch(
        new Request("https://media.example.test/not-media", {
          headers: { Origin: "https://customer.test" },
        }),
        { ...env, ...customEnvironment },
        { waitUntil() {} },
      );
      assert.equal(result.status, 503);
      assert.equal(await result.text(), "Domain registry unavailable");
      assert.equal(result.headers.get("Access-Control-Allow-Origin"), null);
    }
  } finally {
    globalThis.caches = originalCaches;
    globalThis.fetch = originalFetch;
  }
});

test("an unregistered browser origin is rejected before token, cache, or origin work", async () => {
  const originalCaches = globalThis.caches;
  const originalFetch = globalThis.fetch;
  globalThis.caches = {
    default: { match: async () => { throw new Error("cache reached"); } },
  };
  globalThis.fetch = async () => { throw new Error("origin reached"); };
  try {
    const result = await worker.fetch(
      new Request("https://media.example.test/media/not-a-real-grant", {
        headers: { Origin: "https://attacker.example" },
      }),
      env,
      { waitUntil() {} },
    );
    assert.equal(result.status, 403);
    assert.equal(result.headers.get("Access-Control-Allow-Origin"), null);
  } finally {
    globalThis.caches = originalCaches;
    globalThis.fetch = originalFetch;
  }
});

test("an invalid token lifetime configuration fails closed", async () => {
  const path = await requestPath();
  const invalidEnv = { ...env, TOKEN_TTL_SECONDS: "901" };
  assert.equal((await worker.fetch(
    new Request(`https://media.example.test${path}`), invalidEnv, { waitUntil() {} },
  )).status, 503);
});

test("missing origin or secret configuration returns a stable 503 before other work", async () => {
  const originalCaches = globalThis.caches;
  const originalFetch = globalThis.fetch;
  globalThis.caches = {
    default: { match: async () => { throw new Error("cache reached"); } },
  };
  globalThis.fetch = async () => { throw new Error("origin reached"); };

  try {
    for (const key of ["CDN_SIGNING_SECRET", "CDN_ORIGIN_SECRET", "ORIGIN_API", "WEB_ORIGIN"]) {
      for (const missingValue of [undefined, "", "   "]) {
        const invalidEnv = { ...env, [key]: missingValue };
        const result = await worker.fetch(
          new Request("https://media.example.test/not-a-media-route", { method: "OPTIONS" }),
          invalidEnv,
          { waitUntil() {} },
        );
        assert.equal(result.status, 503, `${key}=${String(missingValue)}`);
        assert.equal(await result.text(), "CDN edge is misconfigured");
        assert.equal(result.headers.get("Cache-Control"), "no-store");
      }
    }
  } finally {
    globalThis.caches = originalCaches;
    globalThis.fetch = originalFetch;
  }
});
