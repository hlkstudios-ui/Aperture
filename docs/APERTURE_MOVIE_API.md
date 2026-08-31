# Aperture Movie API boundary

The customer storefront never receives a metadata-provider credential. All discovery traffic follows
this server-only path:

```text
browser -> same-origin Next route/server component -> Aperture API -> Aperture Movie API
```

The independent service lives in the sibling repository `../Aperture-Movie-API` and owns upstream
authentication, normalization, opaque IDs, cache policy, retry behavior, tenant keys, rate limits,
and attribution metadata. Do not add it to this npm workspace, import its source by filesystem path,
or share a dotenv file between deployments.

## Aperture configuration

```dotenv
MOVIE_METADATA_MODE=gateway
APERTURE_MOVIE_API_ORIGIN=https://movies.internal.example
APERTURE_MOVIE_API_KEY=amp_live_replace_with_a_per_deployment_key
```

`APERTURE_MOVIE_API_KEY` is server-only. It must never be renamed with a `NEXT_PUBLIC_` prefix or
returned by an API route. `legacy` mode remains available only as a migration fallback while the local
catalog projection and historical provider IDs are reconciled.

Current gateway cutover covers:

- universal public search;
- 100 specialist discovery rails;
- provider-neutral discovered-title detail pages;
- the private owner's movie search/import flow;
- private dashboard trending metadata.

The local PostgreSQL catalog remains authoritative for publication, playback rights, CDN sources,
viewer entitlements, progress, curation, and homepage editorial snapshots. Those records are not
upstream metadata and must not be moved blindly into a public catalog API.

## Studio privacy

Studio is an owner control plane, not part of the public product navigation. Public builds expose no
Studio link or copy; public production requests receive an indistinguishable `404`; accepted private
responses are `no-store` and `noindex`. Local owner access remains available by entering `/studio`
directly.

This runtime boundary does not make Studio source code invisible to somebody who receives this whole
repository. A commercial template release must be produced from a storefront-only distribution that
omits `apps/web/app/studio`, its private API routes, owner deployment manifests, and secrets. Long term,
Studio should move into an owner-only application beside Aperture Movie API.

## Licensing gate

TMDB's standard developer terms do not permit the planned commercial resale/sublicensing model. The
Movie API production runtime therefore refuses to start until a written commercial agreement has
been obtained and `TMDB_COMMERCIAL_LICENSE_CONFIRMED=true` is deliberately configured. Required
provider attribution remains in `/data-credits` unless that written agreement explicitly changes it.
