import { describe, expect, it } from "vitest";

import {
  STUDIO_EDGE_HEADER,
  studioEdgeHeaders,
  studioEdgeRequired,
  validStudioEdgeValue,
} from "./studio-edge";

const secret = "owner-private-edge-secret-that-is-long-enough";

describe("private Studio edge", () => {
  it("fails closed in production even when the explicit flag is omitted", () => {
    const env = { NODE_ENV: "production" } as NodeJS.ProcessEnv;
    expect(studioEdgeRequired(env)).toBe(true);
    expect(validStudioEdgeValue(null, env)).toBe(false);
    expect(validStudioEdgeValue(secret, env)).toBe(false);
    expect(() => studioEdgeHeaders(env)).toThrow("not configured");
  });

  it("accepts only the exact private value when the boundary is enabled", () => {
    const env = {
      NODE_ENV: "production",
      STUDIO_EDGE_SECRET: secret,
    } as NodeJS.ProcessEnv;
    expect(validStudioEdgeValue(null, env)).toBe(false);
    expect(validStudioEdgeValue(`${secret}x`, env)).toBe(false);
    expect(validStudioEdgeValue("x".repeat(secret.length), env)).toBe(false);
    expect(validStudioEdgeValue(secret, env)).toBe(true);
    expect(studioEdgeHeaders(env)).toEqual({ [STUDIO_EDGE_HEADER]: secret });
  });

  it("keeps the local owner workflow available outside the private deployment", () => {
    const env = {
      NODE_ENV: "development",
      APP_ENV: "development",
      PRIVATE_STUDIO_REQUIRED: "false",
    } as NodeJS.ProcessEnv;
    expect(studioEdgeRequired(env)).toBe(false);
    expect(validStudioEdgeValue(null, env)).toBe(true);
    expect(studioEdgeHeaders(env)).toEqual({});
  });
});
