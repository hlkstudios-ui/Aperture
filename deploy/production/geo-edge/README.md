# Trusted viewer-region edge

This Worker is the public ingress for the canonical `WEB_HOSTNAME` and verified
Cloudflare-for-SaaS custom hostnames. It removes every client-supplied
`X-Aperture-*` identity header, reads Cloudflare's trusted `request.cf.country`,
adds the existing short-lived HMAC assertion understood by the API, and injects
the admitted hostname as `X-Aperture-Public-Host` plus its HTTPS origin as
`X-Aperture-Public-Origin`. It replaces the private `X-Aperture-Edge-Secret`
used by the API to authenticate that origin. Unknown country and
missing-secret states fail closed. Cloudflare special country markers such as
`XX` and `T1`, and every other non-ISO value, are never signed.

The checked-in configuration disables both `workers.dev` and preview URLs. An initial
deploy therefore creates the Worker without a public endpoint; keep those settings disabled.

## Registrar-neutral customer DNS

Enable Cloudflare for SaaS on the Aperture zone with `ORIGIN_HOSTNAME` as the fallback origin
and an Aperture-owned CNAME target such as `customers.apertures.online`. A customer may keep
their registrar and authoritative DNS provider: they create the ownership-verification record
Cloudflare supplies and point a subdomain CNAME at that target. An apex domain requires that
provider's ALIAS/ANAME or CNAME-flattening support (or a documented Cloudflare apex setup);
never ask the customer to point an A record at the VPS. Create and inspect custom hostnames with
a zone-scoped token that includes Cloudflare `SSL and Certificates:Edit`, plus the least
Workers/KV permissions needed by the deployment automation.

The control plane must keep a new domain `pending` while Cloudflare validates ownership and
issues TLS. Write `status: "active"` to `SITE_DOMAINS` only after both hostname and certificate
states are active. Write a suspended/deleted state before disabling the Cloudflare hostname.
That ordering prevents DNS or certificate lag from bypassing edge admission.

1. Copy `wrangler.toml.example` to the private deployment configuration.
2. Set `ORIGIN_WEB` to the absolute HTTPS Hostinger origin URL (for example,
   `https://origin.apertures.online`),
   never to `WEB_HOSTNAME` (which would create a proxy loop).
   Set `CANONICAL_HOST` to the hostname-only canonical storefront value.
3. Store the same high-entropy value used for the API's
   `GEO_ASSERTION_SECRET` with `npm exec -- wrangler secret put GEO_ASSERTION_SECRET`.
   Also store the
   separate `ORIGIN_EDGE_SECRET` shared only with Hostinger Caddy. The Worker removes any
   client-supplied copy before injecting it; the direct origin returns 404 without it.
   Store `CUSTOM_DOMAIN_EDGE_SECRET` as a third secret, using the exact value
   injected into the Hostinger web and API runtimes. It authenticates the
   trusted public-origin identity and is never a customer-facing token.
4. Leave `CUSTOM_DOMAINS_ENABLED=false` for the initial deployment. Create one
   Workers KV namespace for the site-domain admission registry and bind that same
   namespace to both this Worker and `../cdn` as `SITE_DOMAINS`. Registry keys are
   `hostname:<normalized-lowercase-hostname>` and values are JSON objects whose
   `status` is `pending`, `active`, `suspended`, or `deleted`. An optional
   `hostname` field must exactly match the key. Only `active` is admitted. Publish
   the KV record only after Cloudflare reports both custom-hostname and certificate
   status as active; remove or suspend the record before deleting a hostname.
5. Run `npm ci` and `npm test` from this directory, then deploy the locked CLI with
   `npm run deploy`. Only after the origin and secrets are verified, explicitly bind the
   production `WEB_HOSTNAME` and the Cloudflare-for-SaaS wildcard route in the private
   configuration or Cloudflare dashboard. Add exactly one more-specific no-Worker route for
   `ORIGIN_HOSTNAME`, `STORAGE_HOSTNAME`, and `CDN_HOSTNAME` so the wildcard cannot
   intercept an origin subrequest or take precedence over the CDN Worker Custom Domain.
   A no-Worker route has no script association and must not be declared as a geo-Worker route
   in Wrangler. Then set the Worker `CUSTOM_DOMAINS_ENABLED=true` and redeploy. Run the
   Hostinger `cloudflare_saas_preflight.py` with its separate read-only topology credential;
   only a secret-free `ready:true` result permits the runtime readiness attestation and feature
   flag. Verify allowed, denied, absent, expired, and spoofed-country cases before recording
   production evidence.

The canonical hostname remains available when the custom-domain flag is false. A
non-canonical hostname returns a non-cacheable 404 when the feature is disabled,
missing, unknown, or inactive. Once enabled, a missing/unreadable/malformed KV
registry returns a non-cacheable 503 and never reaches Hostinger. Cloudflare
terminates customer TLS; Caddy obtains certificates only for Aperture-owned origin
hostnames. An active custom host also returns 503 if the custom-domain edge secret
is absent, while the canonical hostname remains available. The Worker source contains
no credentials and the example values are non-deployable.
