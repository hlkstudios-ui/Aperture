# Protected media CDN edge

This Cloudflare Worker is an adjunct CDN edge; the Hostinger VPS remains the application,
database, queue, and private object-storage origin.

The API issues a short-lived HMAC path only after normal session, profile, title, edition,
rights, and source authorization. The worker verifies that grant before cache lookup. Cache
keys omit the grant but retain the immutable playback-source/object path. A miss reaches the
Hostinger `/api/edge-media` origin with a separate secret; that origin revalidates the
grant, active session, current rights, source ownership, and object path. Range requests are
forwarded without cache insertion. Raw masters have no playback source and cannot be named.

Copy `wrangler.toml.example` to the git-ignored `wrangler.toml`, replace only public origins,
and inject both secrets with the provider secret manager. Dummy testing must use the local
worker harness and fake secrets; do not deploy until Hostinger and CDN credentials exist.

## Local fake-credential verification

No account or network access is required:

```bash
npm test --prefix deploy/production/cdn
```

The harness proves grant validation occurs before cache access, a valid immutable object is
cached across grants, tampered/expired requests never reach origin, byte ranges bypass cache,
and an invalid token-lifetime configuration fails closed.

## Credential-last deployment

1. Copy `wrangler.toml.example` to `wrangler.toml` and replace the dummy API/web origins.
2. Set the same 300-second token lifetime used by the API. Do not increase it without an
   explicit revocation-lag review.
3. Inject `CDN_SIGNING_SECRET` and `CDN_ORIGIN_SECRET` with `wrangler secret put`; use the
   exact values injected into the Hostinger VPS environment and never put them in source.
4. Deploy the worker, map `CDN_HOSTNAME` to it, and set `CDN_PUBLIC_ORIGIN` plus
   `NEXT_PUBLIC_MEDIA_ORIGIN` to that HTTPS origin before building the production web image.
5. Prove from two regions that an authorized manifest and segment play, a second full GET is
   an edge cache hit, Range returns 206, an expired/tampered path returns 403 before origin,
   origin access without its secret returns 404, CORS admits only the production web origin,
   and raw masters remain inaccessible. Preserve provider request/cache evidence without
   recording signed URLs or secrets.

Edge cache hits intentionally have at most the grant's five-minute session/rights revocation
lag. Misses revalidate current session and rights at the API. Changing that tradeoff requires
a new security review and acceptance run.
