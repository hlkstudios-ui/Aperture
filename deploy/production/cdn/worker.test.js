import assert from "node:assert/strict";
import test from "node:test";

import worker, { signature } from "./worker.js";

const env = {
  CDN_SIGNING_SECRET: "dummy-signing-secret-with-at-least-32-characters",
  CDN_ORIGIN_SECRET: "dummy-origin-secret-with-at-least-32-characters",
  ORIGIN_API: "https://watch.example.test/api",
  WEB_ORIGIN: "https://watch.example.test",
  TOKEN_TTL_SECONDS: "300",
};

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
  const first = await worker.fetch(new Request(`https://media.example.test${path}`), env, context);
  assert.equal(first.status, 200);
  assert.equal(first.headers.get("Access-Control-Allow-Origin"), env.WEB_ORIGIN);
  await new Promise((resolve) => setTimeout(resolve, 0));
  const second = await worker.fetch(new Request(`https://media.example.test${path}`), env, context);
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
      headers: { "Content-Range": "bytes 2-5/10", "Accept-Ranges": "bytes" },
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
});

test("an invalid token lifetime configuration fails closed", async () => {
  const path = await requestPath();
  const invalidEnv = { ...env, TOKEN_TTL_SECONDS: "901" };
  assert.equal((await worker.fetch(
    new Request(`https://media.example.test${path}`), invalidEnv, { waitUntil() {} },
  )).status, 503);
});
