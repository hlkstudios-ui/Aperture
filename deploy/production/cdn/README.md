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
The worker returns a non-cacheable 503 before routing or cache access if either origin or
either required secret is absent.
The checked-in configuration disables both `workers.dev` and preview URLs. An initial
deploy therefore creates the Worker without a public endpoint; keep those settings disabled.

Browser CORS is admitted independently from media-grant authorization. The canonical
`WEB_ORIGIN` is always eligible and does not depend on a custom-domain registry. An
optional custom origin is echoed only when `CUSTOM_DOMAINS_ENABLED=true` and the shared
`SITE_DOMAINS` record at `hostname:<lowercase-hostname>` is valid JSON with
`status: "active"`. Pending, suspended, deleted, unknown, non-HTTPS, or nonstandard-port origins
receive a non-cacheable 403 with no `Access-Control-Allow-Origin`; an unavailable or
malformed enabled registry receives 503. Requests without an `Origin` header may fetch a
valid signed object for non-browser clients, but receive no CORS allowance, and preflights
without an admitted origin fail closed.

## Local fake-credential verification

No account or network access is required:

```bash
npm ci --prefix deploy/production/cdn
npm test --prefix deploy/production/cdn
```

The harness proves grant validation occurs before cache access, a valid immutable object is
cached across grants, tampered/expired requests never reach origin, byte ranges bypass cache,
and an invalid token-lifetime configuration fails closed.

## Credential-last deployment

1. Copy `wrangler.toml.example` to `wrangler.toml` and replace the dummy API/web origins. For
   Hostinger, `ORIGIN_API` is `https://ORIGIN_HOSTNAME/api` (the credential-protected direct
   origin), never the geo Worker hostname, because the geo edge intentionally replaces
   client origin headers. DigitalOcean uses its allowlisted `/api/edge-media` ingress.
2. Set the same 300-second token lifetime used by the API. Do not increase it without an
   explicit revocation-lag review.
3. Inject `CDN_SIGNING_SECRET` and `CDN_ORIGIN_SECRET` with
   `npm exec -- wrangler secret put`; use the exact values injected into the Hostinger VPS
   environment and never put them in source.
4. Leave `CUSTOM_DOMAINS_ENABLED=false` until the geo edge setup has created and populated
   the production `SITE_DOMAINS` Workers KV namespace. Bind the exact same namespace to this
   Worker, verify its active/pending/suspended/deleted lifecycle, then enable the flag.
   Removing or suspending a KV record revokes that customer's browser CORS without changing
   canonical `WEB_ORIGIN` access.
5. Deploy the pinned CLI with `npm run deploy`. Only after the origin and secrets are
   verified, explicitly bind `CDN_HOSTNAME` as a Worker Custom Domain for this exact script in
   the private configuration or Cloudflare dashboard. Keep the separate no-script
   `CDN_HOSTNAME/*` zone-route exclusion required by the geo wildcard. Run the Hostinger
   `cloudflare_saas_preflight.py`; it verifies the mapping, route exclusion, shared KV binding,
   Worker flag, and safe runtime-token reads without mutating Cloudflare. Then set
   `CDN_PUBLIC_ORIGIN` plus the
   server-side web CSP allowlist `MEDIA_SOURCE_ORIGINS` to that HTTPS origin before building.
6. Prove from two regions that an authorized manifest and segment play, a second full GET is
   an edge cache hit, Range returns 206, an expired/tampered path returns 403 before origin,
   origin access without its secret returns 404, CORS admits the canonical web origin and only
   active registered customer origins, and raw masters remain inaccessible. Preserve provider
   request/cache evidence without recording signed URLs or secrets.

Edge cache hits intentionally have at most the grant's five-minute session/rights revocation
lag. Misses revalidate current session and rights at the API. Changing that tradeoff requires
a new security review and acceptance run.
