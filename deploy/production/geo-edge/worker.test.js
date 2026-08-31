import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import worker, { geoSignature } from "./worker.js";

const env = {
  ORIGIN_WEB: "https://aperture-origin.example.test",
  CANONICAL_HOST: "watch.example.test",
  CUSTOM_DOMAINS_ENABLED: "false",
  GEO_ASSERTION_SECRET: "dummy-geo-assertion-secret-at-least-32-characters",
  ORIGIN_EDGE_SECRET: "dummy-origin-edge-secret-at-least-32-characters",
  CUSTOM_DOMAIN_EDGE_SECRET: "dummy-custom-domain-edge-secret-at-least-32-characters",
};

test("checked-in deployment config exposes no public preview endpoint", () => {
  const config = readFileSync(new URL("./wrangler.toml.example", import.meta.url), "utf8");
  assert.match(config, /^workers_dev = false$/m);
  assert.match(config, /^preview_urls = false$/m);
});

function geoRequest(country, spoofed = false) {
  const request = new Request("https://watch.example.test/api/catalog/movies?q=film", {
    headers: spoofed
      ? {
          "X-Aperture-Country": "US",
          "X-Aperture-Geo-Timestamp": "1",
          "X-Aperture-Geo-Signature": "attacker",
          "X-Aperture-Public-Host": "attacker.example",
          "X-Aperture-Public-Origin": "https://attacker.example",
          "X-Aperture-Edge-Secret": "attacker",
          "X-Aperture-Site-Id": "attacker",
          "X-Forwarded-Host": "attacker.example",
        }
      : {},
  });
  Object.defineProperty(request, "cf", { value: { country } });
  return request;
}

test("trusted edge country replaces spoofed assertions and preserves path", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (request) => {
    assert.equal(new URL(request.url).host, "aperture-origin.example.test");
    assert.equal(new URL(request.url).pathname, "/api/catalog/movies");
    assert.equal(request.headers.get("X-Aperture-Country"), "CA");
    assert.notEqual(request.headers.get("X-Aperture-Geo-Signature"), "attacker");
    assert.equal(request.headers.get("X-Aperture-Public-Host"), env.CANONICAL_HOST);
    assert.equal(
      request.headers.get("X-Aperture-Public-Origin"),
      `https://${env.CANONICAL_HOST}`,
    );
    assert.equal(
      request.headers.get("X-Aperture-Edge-Secret"),
      env.CUSTOM_DOMAIN_EDGE_SECRET,
    );
    assert.equal(request.headers.get("X-Forwarded-Host"), env.CANONICAL_HOST);
    assert.equal(request.headers.get("X-Aperture-Site-Id"), null);
    assert.equal(request.headers.get("X-Aperture-Origin-Secret"), env.ORIGIN_EDGE_SECRET);
    const timestamp = request.headers.get("X-Aperture-Geo-Timestamp");
    assert.equal(
      request.headers.get("X-Aperture-Geo-Signature"),
      await geoSignature(env.GEO_ASSERTION_SECRET, "CA", Number(timestamp)),
    );
    return new Response("ok");
  };
  try {
    assert.equal((await worker.fetch(geoRequest("ca", true), env)).status, 200);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("unknown, special, and non-ISO countries fail closed before origin", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    throw new Error("origin must not be reached");
  };
  try {
    for (const country of [undefined, "XX", "T1", "A1", "EU", "ZZ", 42]) {
      const result = await worker.fetch(geoRequest(country), env);
      assert.equal(result.status, 403, `expected ${String(country)} to be rejected`);
      assert.equal(await result.text(), "Viewer region is unavailable");
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("only active custom hostnames in SITE_DOMAINS reach the origin", async () => {
  const records = new Map([
    ["hostname:active.customer.test", { hostname: "active.customer.test", status: "active" }],
    ["hostname:pending.customer.test", { status: "pending" }],
  ]);
  const customEnv = {
    ...env,
    CUSTOM_DOMAINS_ENABLED: "true",
    SITE_DOMAINS: { get: async (key) => records.get(key) ?? null },
  };
  const originalFetch = globalThis.fetch;
  let originRequests = 0;
  globalThis.fetch = async (request) => {
    originRequests += 1;
    assert.equal(request.headers.get("X-Aperture-Public-Host"), "active.customer.test");
    assert.equal(
      request.headers.get("X-Aperture-Public-Origin"),
      "https://active.customer.test",
    );
    assert.equal(
      request.headers.get("X-Aperture-Edge-Secret"),
      env.CUSTOM_DOMAIN_EDGE_SECRET,
    );
    assert.equal(request.headers.get("X-Forwarded-Host"), "active.customer.test");
    return new Response("ok");
  };
  try {
    const active = geoRequest("CA");
    Object.defineProperty(active, "url", { value: "https://active.customer.test/catalog" });
    assert.equal((await worker.fetch(active, customEnv)).status, 200);

    for (const hostname of ["pending.customer.test", "unknown.customer.test"]) {
      const denied = geoRequest("CA");
      Object.defineProperty(denied, "url", { value: `https://${hostname}/catalog` });
      const response = await worker.fetch(denied, customEnv);
      assert.equal(response.status, 404);
      assert.equal(response.headers.get("Cache-Control"), "no-store");
    }
    assert.equal(originRequests, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("custom domains stay disabled without the explicit flag and binding", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error("origin must not be reached"); };
  try {
    const request = geoRequest("CA");
    Object.defineProperty(request, "url", { value: "https://customer.test/catalog" });
    const result = await worker.fetch(request, { ...env, CUSTOM_DOMAINS_ENABLED: undefined });
    assert.equal(result.status, 404);
    assert.equal(await result.text(), "Not found");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("a missing custom-domain edge secret blocks custom hosts but not the canonical host", async () => {
  const customEnv = {
    ...env,
    CUSTOM_DOMAINS_ENABLED: "true",
    CUSTOM_DOMAIN_EDGE_SECRET: "",
    SITE_DOMAINS: {
      get: async () => ({ hostname: "customer.test", status: "active" }),
    },
  };
  const originalFetch = globalThis.fetch;
  let canonicalRequests = 0;
  globalThis.fetch = async (request) => {
    canonicalRequests += 1;
    assert.equal(request.headers.get("X-Aperture-Edge-Secret"), null);
    return new Response("ok");
  };
  try {
    const customRequest = geoRequest("CA");
    Object.defineProperty(customRequest, "url", { value: "https://customer.test/catalog" });
    const denied = await worker.fetch(customRequest, customEnv);
    assert.equal(denied.status, 503);
    assert.equal(await denied.text(), "Custom domain edge is misconfigured");

    assert.equal((await worker.fetch(geoRequest("CA"), customEnv)).status, 200);
    assert.equal(canonicalRequests, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("enabled registry failures and malformed records return 503", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error("origin must not be reached"); };
  try {
    for (const binding of [
      undefined,
      { get: async () => { throw new Error("KV unavailable"); } },
      { get: async () => ({ status: "unexpected" }) },
      { get: async () => ({ hostname: "other.customer.test", status: "active" }) },
    ]) {
      const request = geoRequest("CA");
      Object.defineProperty(request, "url", { value: "https://customer.test/catalog" });
      const result = await worker.fetch(request, {
        ...env,
        CUSTOM_DOMAINS_ENABLED: "true",
        SITE_DOMAINS: binding,
      });
      assert.equal(result.status, 503);
      assert.equal(await result.text(), "Domain registry unavailable");
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("missing secrets fail closed before origin", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    throw new Error("origin must not be reached");
  };
  try {
    assert.equal(
      (await worker.fetch(geoRequest("CA"), { ...env, GEO_ASSERTION_SECRET: "" })).status,
      503,
    );
    assert.equal(
      (await worker.fetch(geoRequest("CA"), { ...env, ORIGIN_EDGE_SECRET: "" })).status,
      503,
    );
    assert.equal(
      (await worker.fetch(geoRequest("CA"), { ...env, CANONICAL_HOST: "" })).status,
      503,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});
