# Optional customer domains

A custom domain is an optional front door for the single owner-controlled Aperture installation.
With no custom domain, the published site continues to work at `WEB_ORIGIN`. While a domain is
being verified, and after one is activated or removed, that Aperture-hosted address remains a safe
fallback. Attaching a domain changes routing and public links only; it does not create a second
catalog, Studio, customer database, or playback stack.

Businesses renting Aperture require separate tenant cells and a control-plane hostname-to-cell
mapping; adding more domains to this installation is not multi-business tenancy. The target model is
documented in [Tenant monetization architecture](TENANT_MONETIZATION.md).

This is registrar-neutral. A domain may be registered at Hostinger, GoDaddy, SiteGround,
Namecheap, or another registrar. The records must be added wherever the domain's authoritative DNS
is actually hosted, which can be different from the registrar.

## Customer flow

1. The owner opens **Studio > Domains** and enters a hostname, not a URL. A subdomain such as
   `watch.example.com` or `www.example.com` is recommended.
2. Aperture registers the hostname with Cloudflare for SaaS and displays the exact DNS records.
3. The owner copies the displayed CNAME and any ownership/certificate TXT or CNAME records into
   their DNS provider. They must not point an A record directly at the Hostinger VPS.
4. **Check connection** refreshes ownership and TLS state. Aperture never admits a pending hostname.
5. Once both the hostname and certificate are ready, **Make primary** publishes the edge allowlist
   entry last. The custom address and the Aperture fallback then reach the same application.
6. **Use Aperture-hosted address as primary** switches public links and search indexing back to the
   Aperture address without disconnecting any active custom aliases. The owner can make an active
   custom domain primary again later.
7. Removal withdraws edge admission first, then removes the provider hostname. Unknown, pending,
   suspended, and removed hostnames fail closed.

DNS labels and field names differ between providers. Some DNS consoles want only the relative host
(`watch` or `_acme-challenge.watch`) rather than the full hostname; Studio shows the authoritative
record value, while the DNS provider's documentation determines its input convention. DNS and
certificate propagation can take time, so the operation is deliberately asynchronous.

### Apex domains

Ordinary DNS does not allow a CNAME at the zone apex. Prefer `www.example.com` or
`watch.example.com`, which works across the widest range of DNS providers. An apex such as
`example.com` is suitable only when its DNS provider supports ALIAS, ANAME, or CNAME flattening, or
when a separately approved Cloudflare apex-proxying arrangement exists. Domain registration at a
particular company does not by itself guarantee apex support.

## Runtime boundary

```text
customer hostname
  -> DNS CNAME to CUSTOM_DOMAIN_CNAME_TARGET
  -> Cloudflare for SaaS ownership and TLS
  -> geo edge Worker + active SITE_DOMAINS KV admission
  -> protected origin.apertures.online
  -> existing Caddy, Next.js, and FastAPI services
```

Cloudflare terminates customer-hostname TLS. Caddy continues to hold certificates only for
Aperture-owned origin names. The geo Worker removes spoofed Aperture headers, admits the canonical
host unconditionally, looks up custom hosts in the active registry, and sends an authenticated
public-host assertion to the private application boundary. The same registry limits CDN CORS to the
canonical storefront and active custom origins.

Customer and administrator cookies remain host-only. A viewer who changes from the Aperture address
to a custom address may need to sign in again; a cookie is never widened across unrelated domains.
Password-reset links, billing returns, and authentication handoffs stay bound to the validated
hostname where the operation began, with the Aperture origin as the safe fallback.

Customer browsers call FastAPI through the same-origin Next.js gateway on whichever front door they
opened. FastAPI's own browser CORS list therefore remains static; the protected-media CDN applies a
separate registry-backed CORS policy for the canonical address and active custom domains. All
connected addresses remain usable, but only the owner-selected primary front door is indexable;
other aliases emit `noindex, follow` to avoid duplicate search listings without forced redirects.

OAuth providers keep one stable Aperture-owned callback. PKCE state is held server-side; after the
provider returns, a short-lived single-use handoff is redeemed on the verified originating domain,
which sets that domain's normal host-only session cookie. Session tokens are never placed in a URL.

When Turnstile CAPTCHA is enabled, every customer hostname must also be admitted by the configured
Turnstile widget (or routed to an approved widget for that hostname). The API compares Siteverify's
returned hostname with the verified storefront origin and rejects tokens issued for another site.
Activation and removal update that widget fail-closed through a distinct Turnstile Sites Write
token. This non-Enterprise launch supports ten widget hostnames: one canonical Aperture hostname
plus at most nine configured custom domains.

## Configuration and activation

Custom domains default to disabled and are unavailable unless every required setting is valid:

```dotenv
CUSTOM_DOMAINS_ENABLED=false
CUSTOM_DOMAIN_INFRASTRUCTURE_READY=false
CUSTOM_DOMAIN_PROVIDER=cloudflare
CUSTOM_DOMAIN_CNAME_TARGET=customers.apertures.online
CUSTOM_DOMAIN_FALLBACK_ORIGIN=origin.apertures.online
CUSTOM_DOMAIN_MAX_PER_SITE=9
CUSTOM_DOMAIN_EDGE_SECRET=<independent random secret, at least 32 characters>
CLOUDFLARE_CUSTOM_HOSTNAMES_API_TOKEN=<server-side runtime token>
CLOUDFLARE_TURNSTILE_API_TOKEN=<separate Turnstile Sites Write runtime token>
TURNSTILE_HOSTNAME_LIMIT=10
CLOUDFLARE_CUSTOM_DOMAIN_PREFLIGHT_API_TOKEN=<temporary read-only owner token>
CLOUDFLARE_ZONE_ID=<32 hex characters>
CLOUDFLARE_ACCOUNT_ID=<32 hex characters>
CLOUDFLARE_SITE_DOMAINS_KV_NAMESPACE_ID=<32 hex characters>
CLOUDFLARE_GEO_EDGE_SCRIPT_NAME=aperture-production-geo-edge
CLOUDFLARE_CDN_SCRIPT_NAME=aperture-protected-media
```

Use a dedicated runtime token with only the zone Custom Hostnames / SSL-certificate permissions and
account Workers KV edit permission needed for this integration. Do not reuse a temporary DNS-cutover
token or the separate read-only preflight token. Bind the same `SITE_DOMAINS` KV namespace to both
Workers, configure the active SaaS fallback origin and proxied CNAME target, and map `CDN_HOSTNAME`
to the CDN Worker as a Worker Custom Domain. The geo wildcard route requires more-specific no-script
exclusions for the origin, storage, and CDN hostnames so it cannot recurse into origins or intercept
the CDN mapping.

Deploy with both local flags false and prove canonical traffic first. Run the GET-only
`deploy/production/hostinger/cloudflare_saas_preflight.py` from the owner workstation. It verifies
the fallback, CNAME, wildcard and exclusion routes, CDN mapping, both Worker flags/KV bindings, geo
secrets, safe reads with the custom-domain runtime token, and the Turnstile widget's canonical-host
and quota shape. Only its secret-free `ready:true` result may be recorded as
`CUSTOM_DOMAIN_INFRASTRUCTURE_READY=true`; the production validator rejects an enabled feature
without that attestation. Clear and revoke the temporary preflight token afterward,
and set readiness false before any topology or credential change. The canonical Aperture hostname
remains available whether custom domains are disabled, pending, active, or later removed.

Studio also provides an owner-triggered reconciliation action for provider and edge state. Workers
KV is eventually consistent, so admission changes can take a short propagation window to reach
every edge location. Production operations should run reconciliation after out-of-band Cloudflare
changes; automated scheduled reconciliation and a serialized operation outbox remain recommended
hardening for a future multi-tenant service.

The current repository intentionally has one `SiteBrandConfiguration` and no tenant key on users,
catalog, billing, playback, storage, analytics, or caches. Therefore these domains are aliases for
one installation. Hosting many unrelated business owners in one database requires tenant isolation
across those domains before hostname routing can safely select different brands or data. Under the
chosen near-term model, a future control plane must route each business hostname to its separately
provisioned cell rather than selecting a different business inside this shared installation.
