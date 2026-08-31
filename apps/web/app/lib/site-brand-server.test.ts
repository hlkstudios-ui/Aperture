import { afterEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_SITE_BRAND, type SiteBrand } from "@/app/lib/site-brand";
import { getSiteBrand, SiteBrandUnavailableError } from "@/app/lib/site-brand-server";

const publishedBrand: SiteBrand = {
  schema_version: 1,
  revision: 8,
  business_name: "Northstar Pictures",
  short_name: "Northstar",
  tagline: "Find your north.",
  description: "A private cinema, made public.",
  logo_url: "/site/brand/logo?revision=8",
  logo_revision: 8,
  logo_mark: null,
  palette: {
    accent: "#60a5fa",
    accent_hover: "#93c5fd",
    on_accent: "#000000",
    surface: "#070b14",
    surface_elevated: "#111827",
    text: "#f8fafc",
    text_muted: "#a8b3c4",
  },
  locale: {
    default_locale: "en-GB",
    home_market: "GB",
    currency: "GBP",
  },
  published_at: "2026-08-23T04:05:06Z",
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("getSiteBrand", () => {
  it("loads the public published snapshot through the revalidated server seam", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue(publishedBrand),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(getSiteBrand()).resolves.toEqual(publishedBrand);
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/site\/brand$/),
      { next: { revalidate: 60, tags: ["site-brand"] } },
    );
  });

  it.each([
    ["an unsuccessful response", () => Promise.resolve({ ok: false })],
    ["a malformed response", () => Promise.resolve({ ok: true, json: () => Promise.resolve({ ...publishedBrand, palette: {} }) })],
    ["an unreachable API", () => Promise.reject(new Error("offline"))],
  ])("returns the frozen fallback for %s", async (_name, responseFactory) => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(responseFactory));

    await expect(getSiteBrand()).resolves.toBe(DEFAULT_SITE_BRAND);
  });

  it.each([
    ["an unsuccessful response", () => Promise.resolve({ ok: false, status: 503 })],
    ["a malformed response", () => Promise.resolve({ ok: true, json: () => Promise.resolve({ ...publishedBrand, palette: {} }) })],
    ["an unreachable API", () => Promise.reject(new Error("offline"))],
  ])("fails closed in production for %s", async (_name, responseFactory) => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubGlobal("fetch", vi.fn().mockImplementation(responseFactory));

    await expect(getSiteBrand()).rejects.toBeInstanceOf(SiteBrandUnavailableError);
  });
});
