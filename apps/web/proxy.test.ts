import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { proxy } from "./proxy";

const studioSecret = "test-private-studio-edge-secret-000000000000";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("route proxy authorization boundaries", () => {
  it.each(["/clubs", "/community", "/discover", "/prescription"])(
    "does not require an administrator cookie for customer route %s",
    (path) => {
      const response = proxy(new NextRequest(`https://staging.aperture.test${path}`));
      expect(response.headers.get("location")).toBeNull();
      expect(response.status).toBe(200);
    },
  );

  it("redirects an unauthenticated Studio request to Studio login", () => {
    const response = proxy(new NextRequest("https://staging.aperture.test/studio/uploads"));
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "https://staging.aperture.test/studio/login?next=%2Fstudio%2Fuploads",
    );
    expect(response.headers.get("cache-control")).toContain("no-store");
    expect(response.headers.get("x-robots-tag")).toContain("noindex");
  });

  it("lets the explicit Studio bootstrap reach its independently protected route handler", () => {
    const bootstrap = proxy(new NextRequest(
      "http://localhost:3000/studio/dev-access?next=%2Fstudio",
    ));
    expect(bootstrap.status).toBe(200);

    const protectedStudio = proxy(new NextRequest("http://localhost:3000/studio/uploads"));
    expect(protectedStudio.status).toBe(307);
    expect(protectedStudio.headers.get("location")).toBe(
      "http://localhost:3000/studio/login?next=%2Fstudio%2Fuploads",
    );
  });

  it("keeps owner auto-access private while preserving direct local Studio entry", () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("APP_ENV", "development");
    vi.stubEnv("STUDIO_DEV_AUTO_LOGIN", "true");

    const response = proxy(new NextRequest("http://localhost:3000/studio?view=overview"));
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "http://localhost:3000/studio/dev-access?next=%2Fstudio%3Fview%3Doverview",
    );
  });

  it("returns a non-disclosing 404 when private Studio ingress is required", () => {
    process.env.PRIVATE_STUDIO_REQUIRED = "true";
    process.env.STUDIO_EDGE_SECRET = studioSecret;
    try {
      const publicResponse = proxy(new NextRequest("https://watch.aperture.test/studio/login"));
      expect(publicResponse.status).toBe(404);
      expect(publicResponse.headers.get("cache-control")).toContain("no-store");
      expect(publicResponse.headers.get("x-robots-tag")).toContain("noindex");

      const privateResponse = proxy(new NextRequest("https://watch.aperture.test/studio/login", {
        headers: { "x-aperture-studio-edge": studioSecret },
      }));
      expect(privateResponse.status).toBe(200);

      const publicAdminApi = proxy(
        new NextRequest("https://watch.aperture.test/api/gateway/admin/site/brand"),
      );
      expect(publicAdminApi.status).toBe(404);
      expect(publicAdminApi.headers.get("cache-control")).toContain("no-store");

      const privateAdminApi = proxy(
        new NextRequest("https://watch.aperture.test/api/gateway/admin/site/brand", {
          headers: { "x-aperture-studio-edge": studioSecret },
        }),
      );
      expect(privateAdminApi.status).toBe(200);
    } finally {
      delete process.env.PRIVATE_STUDIO_REQUIRED;
      delete process.env.STUDIO_EDGE_SECRET;
    }
  });

  it("fails closed for Studio in production when the private flag is missing", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("PRIVATE_STUDIO_REQUIRED", "false");
    vi.stubEnv("STUDIO_EDGE_SECRET", "");

    const response = proxy(new NextRequest("https://watch.aperture.test/studio"));
    expect(response.status).toBe(404);
    expect(response.headers.get("location")).toBeNull();
    expect(response.headers.get("x-robots-tag")).toContain("noindex");
  });
});
