import { readFileSync, readdirSync } from "node:fs";
import { relative, resolve, sep } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import nextConfig from "../next.config";
import { browserApiPrefixes } from "./lib/api-gateway-policy";

function sources(root: string): string[] {
  const result: string[] = [];
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    const absolute = resolve(root, entry.name);
    if (entry.isDirectory()) {
      result.push(...sources(absolute));
    } else if (/\.(?:ts|tsx)$/.test(entry.name) && !/\.test\.(?:ts|tsx)$/.test(entry.name)) {
      result.push(absolute);
    }
  }
  return result;
}

describe("browser API-origin boundary", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("keeps public API configuration out of production web sources", () => {
    const webRoot = resolve(process.cwd());
    const inspected = [resolve(webRoot, "next.config.ts"), ...sources(resolve(webRoot, "app"))];
    const leaks = inspected.flatMap((file) => {
      const source = readFileSync(file, "utf8");
      return source.includes("NEXT_PUBLIC_API_ORIGIN")
        ? [relative(webRoot, file).split(sep).join("/")]
        : [];
    });

    expect(leaks, `Public API-origin configuration leaked into: ${leaks.join(", ")}`).toEqual([]);
  });

  it("keeps upstream origins and development API hosts out of client modules", () => {
    const appRoot = resolve(process.cwd(), "app");
    const leaks = sources(appRoot).flatMap((file) => {
      const source = readFileSync(file, "utf8");
      if (!/^\s*["']use client["'];/m.test(source)) return [];
      return /process\.env\.API_ORIGIN|https?:\/\/(?:localhost|127\.0\.0\.1):800[01]/.test(source)
        ? [relative(appRoot, file).split(sep).join("/")]
        : [];
    });

    expect(leaks, `Client modules contain an upstream API address: ${leaks.join(", ")}`).toEqual([]);
  });

  it("defines a least-reachability gateway and keeps signed catalog BFF routes", async () => {
    const config = readFileSync(resolve(process.cwd(), "next.config.ts"), "utf8");
    const gateway = readFileSync(
      resolve(process.cwd(), "app/api/gateway/[[...path]]/route.ts"),
      "utf8",
    );
    const browse = readFileSync(resolve(process.cwd(), "app/browse/browse-experience.tsx"), "utf8");
    const filter = readFileSync(resolve(process.cwd(), "app/components/catalog-filter-browser.tsx"), "utf8");
    const auth = readFileSync(resolve(process.cwd(), "app/login/auth-form.tsx"), "utf8");

    expect(nextConfig.rewrites).toBeUndefined();
    expect(browserApiPrefixes).toEqual([
      "account",
      "admin",
      "analytics",
      "auth",
      "cinephile",
      "clubs",
      "community",
      "curation",
      "playback",
      "profiles",
      "recommendations",
      "scene-intelligence",
    ]);
    for (const forbidden of ["billing", "edge-media", "health", "metrics", "operations", "ready"]) {
      expect(browserApiPrefixes).not.toContain(forbidden);
    }
    expect(config).toContain("process.env.API_ORIGIN");
    expect(config).not.toContain("NEXT_PUBLIC_API_ORIGIN");
    expect(config).not.toContain("destination: `${apiOrigin}");
    expect(config).toContain('serverActions: { bodySizeLimit: "3mb" }');
    expect(gateway).toContain('redirect: "manual"');
    expect(gateway).toContain('headers.append("Set-Cookie", cookie)');
    expect(gateway).toContain('"private, no-store, max-age=0, must-revalidate"');
    expect(gateway).toContain('[...vary, "Cookie"]');
    expect(browse).toContain("/api/catalog/browse");
    expect(filter).toContain("/api/catalog/search");
    expect(auth).toContain("window.location.assign(apiGatewayPath(");
  });

  it("admits only the Turnstile script and frame host when captcha is configured", async () => {
    vi.stubEnv("CAPTCHA_REQUIRED", "true");
    vi.stubEnv("NEXT_PUBLIC_TURNSTILE_SITE_KEY", "public-site-key");
    const enabled = await nextConfig.headers?.();
    const hsts = enabled?.[0]?.headers.find(
      (header) => header.key === "Strict-Transport-Security",
    )?.value;
    expect(hsts).toBe("max-age=31536000");
    const enabledPolicy = enabled
      ?.flatMap((rule) => rule.headers)
      .find((header) => header.key === "Content-Security-Policy")?.value;
    expect(enabledPolicy).toContain(
      "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' https://challenges.cloudflare.com",
    );
    expect(enabledPolicy).toContain("frame-src 'self' https://challenges.cloudflare.com");
    expect(enabledPolicy).toContain("connect-src 'self'");
    expect(enabledPolicy).not.toContain("connect-src 'self' https://challenges.cloudflare.com");

    vi.stubEnv("CAPTCHA_REQUIRED", "false");
    const disabled = await nextConfig.headers?.();
    const disabledPolicy = disabled
      ?.flatMap((rule) => rule.headers)
      .find((header) => header.key === "Content-Security-Policy")?.value;
    expect(disabledPolicy).not.toContain("https://challenges.cloudflare.com");
  });

  it("sets media credentials from the resolved source before native HLS loading", () => {
    const player = readFileSync(
      resolve(process.cwd(), "app/watch/components/adaptive-player.tsx"),
      "utf8",
    );

    expect(player).not.toContain('crossOrigin="use-credentials"');
    expect(player).toMatch(
      /if \(video\.canPlayType\("application\/vnd\.apple\.mpegurl"\)\) \{\s+video\.crossOrigin = mediaUsesApiSession \? "use-credentials" : "anonymous";\s+video\.src = config\.manifest_url;/,
    );
    expect(player).toContain("xhr.withCredentials = mediaUsesApiSession");
  });
});
