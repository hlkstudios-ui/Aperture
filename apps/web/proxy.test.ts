import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { proxy } from "./proxy";

const studioSecret = "test-private-studio-edge-secret-000000000000";

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
  });

  it("returns a non-disclosing 404 when private Studio ingress is required", () => {
    process.env.PRIVATE_STUDIO_REQUIRED = "true";
    process.env.STUDIO_EDGE_SECRET = studioSecret;
    try {
      const publicResponse = proxy(new NextRequest("https://watch.aperture.test/studio/login"));
      expect(publicResponse.status).toBe(404);

      const privateResponse = proxy(new NextRequest("https://watch.aperture.test/studio/login", {
        headers: { "x-aperture-studio-edge": studioSecret },
      }));
      expect(privateResponse.status).toBe(200);
    } finally {
      delete process.env.PRIVATE_STUDIO_REQUIRED;
      delete process.env.STUDIO_EDGE_SECRET;
    }
  });
});
