import { createHash } from "node:crypto";

import { afterEach, describe, expect, it, vi } from "vitest";

import globalSetup from "../../../../tests/e2e/global-setup";
import {
  validateE2EConfiguration,
  verifyApiRuntimeIdentity,
  verifyWebRuntimeIdentity,
  type ApiRuntimeIdentity,
} from "../../../../tests/e2e/safety";

const RUN_ID = "identity-safety01";
const API_ORIGIN = "http://127.0.0.1:18001";
const WEB_ORIGIN = "http://127.0.0.1:13000";
const OWNER_TOKEN = "a".repeat(64);
const OWNER_TOKEN_HASH = createHash("sha256").update(OWNER_TOKEN).digest("hex");

function environment() {
  return {
    APP_ENV: "test",
    STUDIO_DEV_AUTO_LOGIN: "false",
    E2E_RUN_ID: RUN_ID,
    E2E_OWNER_TOKEN: OWNER_TOKEN,
    E2E_BASE_URL: WEB_ORIGIN,
    E2E_API_ORIGIN: API_ORIGIN,
    DATABASE_URL:
      "postgresql+psycopg://fixture:fixture@127.0.0.1:5433/" +
      "aperture_e2e_identity_safety01",
    REDIS_URL: "redis://127.0.0.1:6380/14",
    S3_ENDPOINT: "http://127.0.0.1:9100",
    S3_BUCKET: "aperture-e2e-identity-safety01",
  };
}

function configuration() {
  return validateE2EConfiguration(environment());
}

function installEnvironment() {
  for (const [name, value] of Object.entries(environment())) vi.stubEnv(name, value);
}

function apiIdentity(overrides: Partial<ApiRuntimeIdentity> = {}): ApiRuntimeIdentity {
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

function webIdentity(overrides: Record<string, unknown> = {}) {
  return {
    environment: "test",
    run_id: RUN_ID,
    web_origin: WEB_ORIGIN,
    gateway_target_origin: API_ORIGIN,
    upstream: apiIdentity(),
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("E2E runtime identity verification", () => {
  it("rejects a Redis query that overrides the reserved database", () => {
    expect(() =>
      validateE2EConfiguration({
        ...environment(),
        REDIS_URL: "redis://127.0.0.1:6380/14?db=0",
      }),
    ).toThrow(/query or fragment/);
  });

  it("rejects an API bound to the wrong database", () => {
    expect(() =>
      verifyApiRuntimeIdentity(
        apiIdentity({ database_name: "aperture_e2e_some_other_run" }),
        configuration(),
      ),
    ).toThrow(/API runtime identity mismatch: database/);
  });

  it("rejects an API bound to another Redis owner", () => {
    expect(() =>
      verifyApiRuntimeIdentity(
        apiIdentity({ redis_owner_token_sha256: "b".repeat(64) }),
        configuration(),
      ),
    ).toThrow(/API runtime identity mismatch: Redis owner token/);
  });

  it("rejects a web server configured for a different API", () => {
    const config = configuration();
    const directApi = verifyApiRuntimeIdentity(apiIdentity(), config);

    expect(() =>
      verifyWebRuntimeIdentity(
        {
          environment: "test",
          run_id: RUN_ID,
          web_origin: WEB_ORIGIN,
          gateway_target_origin: "http://127.0.0.1:19001",
          upstream: directApi,
        },
        config,
        directApi,
      ),
    ).toThrow(/Web runtime identity mismatch: gateway target origin/);
  });

  it("stops global setup when the running API uses the wrong resources", async () => {
    installEnvironment();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        Response.json(apiIdentity({ database_name: "aperture_e2e_some_other_run" })),
      ),
    );

    await expect(globalSetup()).rejects.toThrow(/API runtime identity mismatch: database/);
    expect(fetch).toHaveBeenCalledOnce();
  });

  it("stops global setup when the web runtime points at another API", async () => {
    installEnvironment();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(Response.json(apiIdentity()))
        .mockResolvedValueOnce(
          Response.json(
            webIdentity({ gateway_target_origin: "http://127.0.0.1:19001" }),
          ),
        ),
    );

    await expect(globalSetup()).rejects.toThrow(
      /Web runtime identity mismatch: gateway target origin/,
    );
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
