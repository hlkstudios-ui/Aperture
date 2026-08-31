import { describe, expect, it } from "vitest";

import {
  DEFAULT_SITE_BRAND,
  isSiteBrand,
  siteBrandInitials,
  siteBrandLogoSrc,
  type SiteBrand,
} from "@/app/lib/site-brand";

const customBrand: SiteBrand = {
  schema_version: 1,
  revision: 17,
  business_name: "Northstar Pictures Company",
  short_name: "Northstar",
  tagline: "Stories that point home.",
  description: "A hand-picked screen for restless viewers.",
  logo_url: "/site/brand/logo?revision=17",
  logo_revision: 17,
  logo_mark: null,
  palette: {
    accent: "#a78bfa",
    accent_hover: "#c4b5fd",
    on_accent: "#000000",
    surface: "#08070c",
    surface_elevated: "#17131f",
    text: "#faf7ff",
    text_muted: "#b9b0c7",
  },
  locale: {
    default_locale: "fr-CA",
    home_market: "CA",
    currency: "CAD",
  },
  published_at: "2026-08-23T04:05:06Z",
};

describe("site brand contract", () => {
  it("keeps a complete, valid fallback for an unconfigured or unavailable API", () => {
    expect(isSiteBrand(DEFAULT_SITE_BRAND)).toBe(true);
    expect(DEFAULT_SITE_BRAND).toMatchObject({
      schema_version: 1,
      revision: 0,
      business_name: "Aperture",
      short_name: "Aperture",
      logo_url: null,
      published_at: null,
    });
    expect(Object.isFrozen(DEFAULT_SITE_BRAND)).toBe(true);
    expect(Object.isFrozen(DEFAULT_SITE_BRAND.palette)).toBe(true);
    expect(Object.isFrozen(DEFAULT_SITE_BRAND.locale)).toBe(true);
  });

  it("accepts the complete published response shape", () => {
    expect(isSiteBrand(customBrand)).toBe(true);
    expect(isSiteBrand({
      ...customBrand,
      logo_url: null,
      logo_revision: 0,
      logo_mark: { renderer_version: 1, glyph: "q", variant: "ribbon" },
    })).toBe(true);
  });

  it.each([
    ["unknown schema", { ...customBrand, schema_version: 2 }],
    ["blank public name", { ...customBrand, business_name: "   " }],
    ["blank short name", { ...customBrand, short_name: "" }],
    ["invalid palette token", { ...customBrand, palette: { ...customBrand.palette, accent: "hotpink" } }],
    ["missing on-accent token", { ...customBrand, palette: { ...customBrand.palette, on_accent: undefined } }],
    ["missing locale", { ...customBrand, locale: undefined }],
    ["invalid logo revision", { ...customBrand, logo_revision: "17" }],
    ["unsafe logo recipe", { ...customBrand, logo_mark: { renderer_version: 1, glyph: "<", variant: "iris" } }],
    ["unknown logo renderer", { ...customBrand, logo_mark: { renderer_version: 2, glyph: "A", variant: "iris" } }],
    ["competing logo modes", { ...customBrand, logo_mark: { renderer_version: 1, glyph: "A", variant: "iris" } }],
    ["invalid publication timestamp", { ...customBrand, published_at: 123 }],
  ])("rejects a malformed response: %s", (_name, candidate) => {
    expect(isSiteBrand(candidate)).toBe(false);
  });

  it("proxies an opaque API logo path and rejects an arbitrary absolute URL", () => {
    expect(siteBrandLogoSrc(customBrand)).toBe("/api/site/brand/logo?revision=17");

    const absoluteLogo = { ...customBrand, logo_url: "https://cdn.example.test/northstar.webp" };
    expect(siteBrandLogoSrc(absoluteLogo)).toBeNull();
    expect(siteBrandLogoSrc({ ...customBrand, logo_url: null })).toBeNull();
  });

  it("derives a compact fallback mark from at most two words", () => {
    expect(siteBrandInitials(customBrand)).toBe("N");
    expect(siteBrandInitials({ ...customBrand, short_name: "North Star Cinema" })).toBe("NS");
  });
});
