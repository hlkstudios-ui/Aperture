# White-label launch

Every deployed template has one private owner-controlled brand file. Customers never configure
this from the public storefront.

## First launch

1. Provision the owner administrator with `apps/api/scripts/provision_admin.py`.
2. Open the private Studio host and sign in.
3. A first visit to `/studio` opens `/studio/launch` until the first brand has been published.
4. Complete the five stages: Identity, Signature, Palette, Home market, and Premiere.
5. Publish from Premiere. The storefront updates as one versioned release.

Draft saves are resumable and private. Publishing changes public names, logo, metadata, locale,
colors, navigation, footer, authentication surfaces, and customer-facing media labels. It does not
change the catalog, playback sources, subscribers, or internal service identifiers.

The Aperture-hosted storefront remains the default front door. An owner may optionally attach a
registrar-neutral customer hostname without moving the application or data; see
[`CUSTOM_DOMAINS.md`](CUSTOM_DOMAINS.md).

## Private copy assistant

Identity includes an optional AI naming-room assistant for taglines, descriptions, compact names,
and tone directions. Configure it only on the API service:

```dotenv
BRAND_AI_PROVIDER=openai
BRAND_AI_MODEL=gpt-5-mini
BRAND_AI_TIMEOUT_SECONDS=12
BRAND_AI_RATE_LIMIT_PER_HOUR=30
OPENAI_API_KEY=your-server-side-project-key
```

Studio submits through its same-origin server boundary; the provider key and endpoint remain
API-only. Each request produces three strictly validated suggestions. Suggestions remain
ephemeral until the owner explicitly applies one, after which the ordinary draft save and publish
controls still govern the change. Requests are capped per owner, provider calls time out, Responses
API storage is disabled, and prompts or generated copy are not written to application logs or audit
records. If the provider is disabled or unavailable, the current draft remains untouched.

## Logo Atelier

Stage 2 presents a code-built Logo Atelier instead of a public file or URL chooser. Owners can pair
any uppercase `A-Z` or lowercase `a-z` glyph with one of 12 curated constructions, producing 624
case-preserving choices. The draft stores only a strict recipe—`renderer_version`, `glyph`, and an
allowlisted `variant`—and the storefront renders that recipe from repository-owned SVG primitives.
It stores no SVG/XML, paths, filters, fonts, external references, or custom paint values. Generated
marks follow the validated site palette and are previewed at navbar, app-icon, favicon, and
one-colour sizes before publication.

`renderer_version: 1` freezes the meaning of a published recipe. A future visual remapping requires
an explicit renderer-version migration rather than silently changing customer identities. The old
PNG/JPEG/WebP asset endpoints remain only for installations that already have raster branding; the
current wizard does not expose them. Saving a generated mark atomically retires a draft raster, and
publishing it retires the formerly published raster.

## Safety guarantees

- Ownership can be claimed only while exactly one active administrator is provisioned. A second
  active administrator makes an unclaimed launch file fail closed instead of winning a request race.
- Concurrent edits use revision checks and fail with a conflict instead of overwriting work.
- The public endpoint serves only the last published snapshot; an unfinished draft never leaks.
- Legacy uploaded logos must be single-frame PNG, JPEG, or WebP, at most 2 MiB, and between 64 and 4096 pixels per
  side. Pillow verifies the complete container and fully decodes the raster under a bounded pixel
  budget; truncated and decompression-bomb inputs are rejected.
- Arbitrary uploaded SVG/XML, remote logo URLs, raw CSS, and unknown configuration fields are
  rejected. This does not apply to trusted Logo Atelier recipes, which never accept SVG markup.
- Palette text and accent roles require 4.5:1 contrast on both surfaces. Primary button text is
  derived as one black or white `on_accent` token that remains at least 4.5:1 on both the normal and
  hover accent; a palette with no common choice is rejected.
- Studio previews and configuration responses are private and never cached.
- Copy-assistant success and error responses are private and never cached; only the configured site
  owner can invoke the assistant.
- Production storefront rendering fails closed when the branding service is unavailable or returns
  an invalid contract. The built-in Aperture fallback is limited to development and tests; a valid
  unconfigured API response remains the deliberate first-run identity.

Draft and published JSON snapshots carry `schema_version: 1`. Existing unversioned rows are parsed
as legacy v1, while unknown versions are rejected instead of being guessed.

## Ownership recovery

Ownership is never reassigned through an HTTP endpoint. If the stored owner account is irrecoverable,
an operator with database-shell authority must first take and verify a backup, provision or verify the
replacement administrator, and run the offline recovery command from `apps/api`:

```powershell
python scripts/reassign_site_brand_owner.py `
  --current-owner old-owner@example.com `
  --new-owner new-owner@example.com `
  --reason "Owner account lost; incident INC-1234 approved" `
  --confirm "TRANSFER SITE BRAND OWNERSHIP"
```

The command locks the singleton row, verifies both identities and the replacement account's active
state, and writes `site_brand.owner.reassigned` with both immutable administrator IDs and the reason.
Run it only through the production maintenance procedure and retain the resulting audit record.

`Aperture Studio`, protocol headers, cookie names, storage keys, telemetry identifiers, and the
Aperture Movie API remain stable vendor infrastructure. They are intentionally separate from the
buyer’s public business name.
