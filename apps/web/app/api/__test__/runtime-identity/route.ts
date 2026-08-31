import { createHash } from "node:crypto";

import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const privateHeaders = {
  "Cache-Control": "private, no-store, max-age=0",
};

function origin(value: string | undefined): string | null {
  if (!value) return null;
  try {
    const parsed = new URL(value);
    if (
      !["http:", "https:"].includes(parsed.protocol) ||
      parsed.username ||
      parsed.password ||
      parsed.pathname !== "/" ||
      parsed.search ||
      parsed.hash
    ) {
      return null;
    }
    return parsed.origin;
  } catch {
    return null;
  }
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export async function GET(request: Request): Promise<NextResponse> {
  const runId = process.env.E2E_RUN_ID?.trim();
  const ownerToken = request.headers.get("X-Aperture-E2E-Owner");
  if (
    process.env.APP_ENV !== "test" ||
    !runId ||
    request.headers.get("X-Aperture-E2E-Run") !== runId ||
    !ownerToken ||
    !/^[a-f0-9]{64}$/.test(ownerToken)
  ) {
    return new NextResponse(null, { status: 404, headers: privateHeaders });
  }

  const configuredApiOrigin = origin(process.env.API_ORIGIN);
  if (!configuredApiOrigin) {
    return NextResponse.json(
      { detail: "Test runtime identity is unavailable" },
      { status: 503, headers: privateHeaders },
    );
  }

  try {
    const upstreamResponse = await fetch(
      new URL("/__test__/runtime-identity", configuredApiOrigin),
      {
        cache: "no-store",
        headers: {
          "X-Aperture-E2E-Owner": ownerToken,
          "X-Aperture-E2E-Run": runId,
        },
        signal: AbortSignal.timeout(2_000),
      },
    );
    if (!upstreamResponse.ok) {
      return NextResponse.json(
        { detail: "Test API identity is unavailable" },
        { status: 502, headers: privateHeaders },
      );
    }
    const upstream: unknown = await upstreamResponse.json();
    if (
      !record(upstream) ||
      upstream.environment !== "test" ||
      upstream.run_id !== runId ||
      upstream.redis_owner_token_sha256 !==
        createHash("sha256").update(ownerToken).digest("hex") ||
      upstream.api_origin !== configuredApiOrigin
    ) {
      return NextResponse.json(
        { detail: "Test API identity does not match the web runtime" },
        { status: 409, headers: privateHeaders },
      );
    }

    return NextResponse.json(
      {
        environment: "test",
        run_id: runId,
        web_origin: new URL(request.url).origin,
        gateway_target_origin: configuredApiOrigin,
        upstream,
      },
      { headers: privateHeaders },
    );
  } catch {
    return NextResponse.json(
      { detail: "Test API identity is unavailable" },
      { status: 502, headers: privateHeaders },
    );
  }
}
