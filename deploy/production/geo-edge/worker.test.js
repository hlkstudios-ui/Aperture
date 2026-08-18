import assert from "node:assert/strict";
import test from "node:test";

import worker, { geoSignature } from "./worker.js";

const env = {
  ORIGIN_WEB: "https://aperture-origin.example.test",
  GEO_ASSERTION_SECRET: "dummy-geo-assertion-secret-at-least-32-characters",
  ORIGIN_EDGE_SECRET: "dummy-origin-edge-secret-at-least-32-characters",
};

function geoRequest(country, spoofed = false) {
  const request = new Request("https://watch.example.test/api/catalog/movies?q=film", {
    headers: spoofed
      ? {
          "X-Aperture-Country": "US",
          "X-Aperture-Geo-Timestamp": "1",
          "X-Aperture-Geo-Signature": "attacker",
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

test("unknown countries and missing secrets fail closed before origin", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    throw new Error("origin must not be reached");
  };
  try {
    assert.equal((await worker.fetch(geoRequest(undefined), env)).status, 403);
    assert.equal(
      (await worker.fetch(geoRequest("CA"), { ...env, GEO_ASSERTION_SECRET: "" })).status,
      503,
    );
    assert.equal(
      (await worker.fetch(geoRequest("CA"), { ...env, ORIGIN_EDGE_SECRET: "" })).status,
      503,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});
