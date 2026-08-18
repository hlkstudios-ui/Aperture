# Trusted viewer-region edge

This Worker is the public ingress for `WEB_HOSTNAME`. It removes all incoming
`X-Aperture-*` geo headers, reads Cloudflare's trusted `request.cf.country`, and
adds a short-lived HMAC assertion understood by the API. Unknown country and
missing-secret states fail closed.

1. Copy `wrangler.toml.example` to the private deployment configuration.
2. Set `ORIGIN_WEB` to the Hostinger origin hostname,
   never to `WEB_HOSTNAME` (which would create a proxy loop).
3. Store the same high-entropy value used for the API's
   `GEO_ASSERTION_SECRET` with `wrangler secret put GEO_ASSERTION_SECRET`. Also store the
   separate `ORIGIN_EDGE_SECRET` shared only with Hostinger Caddy. The Worker removes any
   client-supplied copy before injecting it; the direct origin returns 404 without it.
4. Deploy, bind `WEB_HOSTNAME`, then verify allowed, denied, absent, expired,
   and spoofed-country cases before recording production evidence.

The Worker contains no credentials and the example values are non-deployable.
