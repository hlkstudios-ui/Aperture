import { describe, expect, it } from "vitest";

import {
  formatTemplatePrice,
  isPlatformAccount,
  isPlatformRegistration,
  isPlatformRental,
  isPlatformVerificationDelivery,
  parseTemplateCollection,
  parseTemplateDetail,
  rentalMatchesIntent,
  templateFeatures,
  type PlatformRental,
} from "./platform-marketplace";

function template(overrides: Record<string, unknown> = {}) {
  return {
    id: "template-1",
    slug: "apertures",
    name: "Apertures",
    description: "A complete cinema platform.",
    category: "Streaming",
    thumbnail_url: "https://assets.example/apertures.webp",
    preview_assets: [{ kind: "image", url: "/marketplace/preview.webp", alt: "Apertures preview" }],
    demo_url: "https://apertures.online",
    status: "published",
    current_version: {
      id: "version-1",
      version: "1.0.0",
      feature_manifest: { features: ["Movies", { label: "Series" }], custom_domains: true },
      configuration_schema: {},
    },
    starting_price: { price_cents: 4900, currency: "USD", interval: "month" },
    rental_available: true,
    unavailable_reason: null,
    ...overrides,
  };
}

describe("platform marketplace response boundary", () => {
  it("parses the versioned collection and exposes only manifest-backed feature chips", () => {
    const parsed = parseTemplateCollection({ schema_version: 1, items: [template()] });

    expect(parsed).not.toBeNull();
    expect(templateFeatures(parsed![0])).toEqual(["Movies", "Series"]);
    expect(formatTemplatePrice(parsed![0].starting_price)).toBe("$49 / month");
  });

  it.each([
    "https://user:secret@assets.example/preview.webp",
    "http://assets.example/preview.webp",
    "//assets.example/preview.webp",
    "https://assets.example\\preview.webp",
    "https://assets.example/preview.webp\nset-cookie:unsafe",
  ])("rejects an unsafe public asset URL: %s", (thumbnailUrl) => {
    expect(parseTemplateCollection({
      schema_version: 1,
      items: [template({ thumbnail_url: thumbnailUrl })],
    })).toBeNull();
  });

  it("requires an exact immutable agreement in template detail", () => {
    const detail = parseTemplateDetail({
      ...template(),
      rental_agreement: {
        id: "agreement-1",
        version: "2026-01",
        title: "Template rental agreement",
        content: "Complete terms",
        content_sha256: "a".repeat(64),
        published_at: "2026-08-31T12:00:00Z",
      },
    });

    expect(detail?.rental_agreement?.content_sha256).toBe("a".repeat(64));
    expect(parseTemplateDetail({ ...template(), rental_agreement: { id: "agreement-1" } })).toBeNull();
  });

  it("parses account verification and explicit registration delivery fields", () => {
    const account = {
      id: "account-1",
      email: "owner@example.com",
      email_verified: false,
      unverified_account_expires_at: "2026-09-02T12:00:00Z",
      created_at: "2026-08-31T12:00:00Z",
    };

    expect(isPlatformAccount(account)).toBe(true);
    expect(isPlatformAccount({ ...account, email_verified: undefined })).toBe(false);
    expect(isPlatformAccount({ ...account, unverified_account_expires_at: "not-a-date" })).toBe(false);
    expect(isPlatformAccount({ ...account, email_verified: true })).toBe(false);
    expect(isPlatformRegistration({
      ...account,
      verification_delivery: "development",
      verification_token_expires_at: "2026-08-31T12:30:00Z",
      development_verification_token: "development-token",
    })).toBe(true);
    expect(isPlatformRegistration({
      ...account,
      verification_delivery: "sent",
      verification_token_expires_at: "2026-08-31T12:30:00Z",
      development_verification_token: null,
    })).toBe(true);
    expect(isPlatformRegistration({
      ...account,
      verification_delivery: "unavailable",
      verification_token_expires_at: null,
      development_verification_token: null,
    })).toBe(true);
    expect(isPlatformRegistration({
      ...account,
      verification_delivery: "sent",
      verification_token_expires_at: null,
      development_verification_token: null,
    })).toBe(false);
    expect(isPlatformVerificationDelivery({
      status: "unavailable",
      verification_token_expires_at: null,
      development_verification_token: null,
    })).toBe(true);
    expect(isPlatformVerificationDelivery({
      status: "sent",
      verification_token_expires_at: null,
      development_verification_token: null,
    })).toBe(false);
    expect(isPlatformVerificationDelivery({
      status: "already_verified",
      verification_token_expires_at: "2026-08-31T12:30:00Z",
      development_verification_token: null,
    })).toBe(false);
  });

  it("requires every nested field before treating a rental response as recorded", () => {
    const rental = {
      schema_version: 1,
      id: "44444444-4444-4444-8444-444444444444",
      status: "awaiting_payment",
      tenant: {
        id: "55555555-5555-4555-8555-555555555555",
        slug: "north-star",
        business_name: "North Star Cinema",
        hosted_hostname: "north-star.apertures.online",
        status: "reserved",
      },
      template: {
        id: "11111111-1111-4111-8111-111111111111",
        slug: "apertures",
        name: "Apertures",
        version_id: "22222222-2222-4222-8222-222222222222",
        version: "1.0.0",
      },
      price_snapshot: { price_cents: 4900, currency: "USD", interval: "month" },
      legal_acceptance: {
        id: "66666666-6666-4666-8666-666666666666",
        agreement_version_id: "33333333-3333-4333-8333-333333333333",
        version: "2026-01",
        content_sha256: "a".repeat(64),
        accepted_at: "2026-08-31T12:30:00Z",
      },
      platform_billing: { status: "disabled", checkout_available: false },
      provisioning_status: "not_started",
      domain_status: "not_created",
      next_action: "platform_billing_unavailable",
      reservation_active: true,
      reservation_expires_at: "2026-09-01T12:30:00Z",
      status_changed_at: "2026-08-31T12:30:00Z",
      expired_at: null,
      created_at: "2026-08-31T12:30:00Z",
    } satisfies PlatformRental;

    expect(isPlatformRental(rental)).toBe(true);
    expect(isPlatformRental({ ...rental, tenant: { ...rental.tenant, business_name: "" } })).toBe(false);
    expect(isPlatformRental({ ...rental, template: { ...rental.template, version_id: "" } })).toBe(false);
    expect(isPlatformRental({ ...rental, price_snapshot: { ...rental.price_snapshot, price_cents: 0 } })).toBe(false);
    expect(isPlatformRental({ ...rental, legal_acceptance: { ...rental.legal_acceptance, accepted_at: "not-a-date" } })).toBe(false);
    expect(isPlatformRental({ ...rental, reservation_active: false })).toBe(false);
    expect(isPlatformRental({ ...rental, reservation_expires_at: "not-a-date" })).toBe(false);
    expect(isPlatformRental({ ...rental, created_at: "not-a-date" })).toBe(false);

    const expired = {
      ...rental,
      status: "expired",
      tenant: { ...rental.tenant, status: "released" },
      next_action: "start_new_rental_request",
      reservation_active: false,
      status_changed_at: "2026-09-01T12:30:00Z",
      expired_at: "2026-09-01T12:30:00Z",
    } satisfies PlatformRental;
    expect(isPlatformRental(expired)).toBe(true);
    expect(isPlatformRental({ ...expired, tenant: { ...expired.tenant, status: "reserved" } })).toBe(false);

    const detail = parseTemplateDetail({
      ...template({
        id: rental.template.id,
        current_version: {
          id: rental.template.version_id,
          version: rental.template.version,
          feature_manifest: {},
          configuration_schema: {},
        },
      }),
      rental_agreement: {
        id: rental.legal_acceptance.agreement_version_id,
        version: rental.legal_acceptance.version,
        title: "Template rental agreement",
        content: "Complete terms",
        content_sha256: rental.legal_acceptance.content_sha256,
        published_at: "2026-08-31T12:00:00Z",
      },
    });
    expect(detail).not.toBeNull();
    expect(rentalMatchesIntent(rental, detail!, "  North   Star Cinema ", "NORTH-STAR")).toBe(true);
    expect(rentalMatchesIntent(
      { ...rental, price_snapshot: { ...rental.price_snapshot, price_cents: 9900 } },
      detail!,
      "North Star Cinema",
      "north-star",
    )).toBe(false);
    expect(rentalMatchesIntent(
      { ...rental, legal_acceptance: { ...rental.legal_acceptance, content_sha256: "b".repeat(64) } },
      detail!,
      "North Star Cinema",
      "north-star",
    )).toBe(false);
  });
});
