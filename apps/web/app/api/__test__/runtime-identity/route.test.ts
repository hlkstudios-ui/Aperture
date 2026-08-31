import { createHash } from "node:crypto";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

const RUN_ID = "identity-safety01";
const API_ORIGIN = "http://127.0.0.1:18001";
const WEB_ORIGIN = "http://127.0.0.1:13000";
const OWNER_TOKEN = "a".repeat(64);
const OWNER_TOKEN_HASH = createHash("sha256").update(OWNER_TOKEN).digest("hex");

function enableTestRuntime() {
  vi.stubEnv("APP_ENV", "test");
  vi.stubEnv("E2E_RUN_ID", RUN_ID);
  vi.stubEnv("API_ORIGIN", API_ORIGIN);
}

function apiIdentity(overrides: Record<string, unknown> = {}) {
  return {
    environment: "test",
    run_id: RUN_ID,
    database_name: "aperture_e2e_identity_safety01",
    s3_bucket: "aperture-e2e-identity-safety01",
    redis_database: 14,
    redis_owner_token_sha256: OWNER_TOKEN_HASH,
    api_origin: API_ORIGIN,
    ...overrides,
  };
}

function request() {
  return new Request(`${WEB_ORIGIN}/api/__test__/runtime-identity`, {
    headers: {
      "X-Aperture-E2E-Owner": OWNER_TOKEN,
      "X-Aperture-E2E-Run": RUN_ID,
    },
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("test-only web runtime identity", () => {
  it("is invisible outside the explicit test environment", async () => {
    vi.stubEnv("APP_ENV", "production");

    const response = await GET(request());

    expect(response.status).toBe(404);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("reports the API target used by the web server", async () => {
    enableTestRuntime();
    vi.mocked(fetch).mockResolvedValue(Response.json(apiIdentity()));

    const response = await GET(request());

    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      environment: "test",
      run_id: RUN_ID,
      web_origin: WEB_ORIGIN,
      gateway_target_origin: API_ORIGIN,
      upstream: apiIdentity(),
    });
    expect(fetch).toHaveBeenCalledWith(
      new URL(`${API_ORIGIN}/__test__/runtime-identity`),
      expect.objectContaining({
        cache: "no-store",
        headers: {
          "X-Aperture-E2E-Owner": OWNER_TOKEN,
          "X-Aperture-E2E-Run": RUN_ID,
        },
      }),
    );
  });

  it("rejects an API from a different test run", async () => {
    enableTestRuntime();
    vi.mocked(fetch).mockResolvedValue(
      Response.json(apiIdentity({ run_id: "different-run01" })),
    );

    const response = await GET(request());

    expect(response.status).toBe(409);
  });
});
