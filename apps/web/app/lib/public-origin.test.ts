import { afterEach, describe, expect, it, vi } from "vitest";

const headerValues = new Map<string, string>();

vi.mock("next/headers", () => ({
  headers: vi.fn(async () => ({
    get: (name: string) => headerValues.get(name.toLowerCase()) ?? null,
  })),
}));

import { currentStorefrontOrigin, primaryStorefrontOrigin } from "./public-origin";

afterEach(() => {
  headerValues.clear();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("storefront origins", () => {
  it("retains the edge-asserted custom hostname", async () => {
    vi.stubEnv("WEB_ORIGIN", "https://apertures.online");
    headerValues.set("x-aperture-public-host", "watch.customer.example");
    headerValues.set("x-forwarded-proto", "https");

    await expect(currentStorefrontOrigin()).resolves.toBe("https://watch.customer.example");
  });

  it("loads the owner-selected primary origin from the internal API", async () => {
    vi.stubEnv("WEB_ORIGIN", "https://apertures.online");
    vi.stubEnv("API_ORIGIN", "http://api:8000");
    const fetchMock = vi.fn(async () => Response.json({
      primary_origin: "https://watch.customer.example",
    }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(primaryStorefrontOrigin()).resolves.toBe("https://watch.customer.example");
    expect(fetchMock).toHaveBeenCalledWith("http://api:8000/site/domain", {
      next: { revalidate: 60, tags: ["site-domain"] },
    });
  });

  it("fails safely to the Aperture-hosted origin", async () => {
    vi.stubEnv("WEB_ORIGIN", "https://apertures.online");
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({
      primary_origin: "https://user:secret@attacker.example/path",
    })));

    await expect(primaryStorefrontOrigin()).resolves.toBe("https://apertures.online");
  });
});
