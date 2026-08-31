import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GET } from "./route";

function enableDevelopmentAccess() {
  vi.stubEnv("NODE_ENV", "development");
  vi.stubEnv("APP_ENV", "development");
  vi.stubEnv("STUDIO_DEV_AUTO_LOGIN", "true");
  vi.stubEnv("API_ORIGIN", "http://localhost:8001");
  vi.stubEnv("WEB_ORIGIN", "http://localhost:3000");
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("Studio development session route", () => {
  it("is unavailable unless the development bypass is explicitly enabled", async () => {
    const response = await GET(new NextRequest("http://localhost:3000/studio/dev-access"));
    expect(response.status).toBe(404);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("rejects non-local and cross-site bootstrap requests", async () => {
    enableDevelopmentAccess();

    const networkResponse = await GET(new NextRequest(
      "http://192.168.1.50:3000/studio/dev-access",
      { headers: { Host: "192.168.1.50:3000" } },
    ));
    const crossSiteResponse = await GET(new NextRequest(
      "http://localhost:3000/studio/dev-access",
      { headers: { Host: "localhost:3000", "Sec-Fetch-Site": "cross-site" } },
    ));

    expect(networkResponse.status).toBe(404);
    expect(crossSiteResponse.status).toBe(404);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("forwards the API-owned session cookie and returns to Studio", async () => {
    enableDevelopmentAccess();
    vi.mocked(fetch).mockResolvedValue(new Response(null, {
      status: 204,
      headers: {
        "Set-Cookie": "aperture_admin_session=local-token; Path=/; HttpOnly; SameSite=Strict",
      },
    }));

    const response = await GET(new NextRequest(
      "http://localhost:3000/studio/dev-access?next=%2Fstudio%2Fuploads%3Fstate%3Dready",
      { headers: { Host: "localhost:3000" } },
    ));

    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8001/admin/auth/development-session",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ Origin: "http://localhost:3000" }),
        cache: "no-store",
      }),
    );
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "http://localhost:3000/studio/uploads?state=ready",
    );
    expect(response.headers.get("set-cookie")).toContain("aperture_admin_session=local-token");
    expect(response.headers.get("cache-control")).toContain("no-store");
  });

  it("reuses an existing valid owner session instead of issuing another one", async () => {
    enableDevelopmentAccess();
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 200 }));

    const response = await GET(new NextRequest(
      "http://localhost:3000/studio/dev-access?next=%2Fstudio%2Fanalytics",
      {
        headers: {
          Cookie: "aperture_admin_session=existing-token",
          Host: "localhost:3000",
        },
      },
    ));

    expect(fetch).toHaveBeenCalledOnce();
    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8001/admin/auth/me",
      expect.objectContaining({
        headers: expect.objectContaining({
          cookie: "aperture_admin_session=existing-token",
        }),
      }),
    );
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "http://localhost:3000/studio/analytics",
    );
    expect(response.headers.get("set-cookie")).toBeNull();
  });

  it("rejects an external return target and fails safely when the API is unavailable", async () => {
    enableDevelopmentAccess();
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 404 }));

    const response = await GET(new NextRequest(
      "http://localhost:3000/studio/dev-access?next=https%3A%2F%2Fattacker.test%2Fsteal",
      { headers: { Host: "localhost:3000" } },
    ));

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "http://localhost:3000/studio/login?manual=1&error=development-access-unavailable",
    );
    expect(response.headers.get("set-cookie")).toBeNull();
  });
});
