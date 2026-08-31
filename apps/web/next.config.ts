import { loadEnvConfig } from "@next/env";
import type { NextConfig } from "next";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// Next preloads env for apps/web before evaluating this config. Force a second
// load from the monorepo root so the single canonical dotenv file wins.
loadEnvConfig(
  resolve(dirname(fileURLToPath(import.meta.url)), "../.."),
  process.env.NODE_ENV === "development",
  console,
  true,
);

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  experimental: {
    // The application/API enforce the 2 MiB logo limit. This allowance covers
    // multipart encoding overhead before the Server Action performs that check.
    serverActions: { bodySizeLimit: "3mb" },
  },
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "image.tmdb.org", pathname: "/t/p/**" },
      { protocol: "https", hostname: "www.themoviedb.org", pathname: "/assets/**" },
    ],
  },
  async headers() {
    const objectStorageOrigin = process.env.NEXT_PUBLIC_OBJECT_STORAGE_ORIGIN;
    const turnstileOrigin =
      process.env.CAPTCHA_REQUIRED === "true" &&
      Boolean(process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY?.trim())
        ? " https://challenges.cloudflare.com"
        : "";
    const internalApiOrigins = new Set(
      [process.env.API_ORIGIN]
        .filter((value): value is string => Boolean(value))
        .map((value) => {
          try { return new URL(value).origin; } catch { return ""; }
        })
        .filter(Boolean),
    );
    const licensedMediaOrigins = (process.env.MEDIA_SOURCE_ORIGINS ?? "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
    const externalSources = [objectStorageOrigin, ...licensedMediaOrigins]
      .filter((value): value is string => typeof value === "string" && /^https?:\/\//.test(value))
      .filter((value) => {
        try { return !internalApiOrigins.has(new URL(value).origin); } catch { return false; }
      });
    const uniqueExternalSources = [...new Set(externalSources)];
    const policy = [
      "default-src 'self'",
      "base-uri 'self'",
      "frame-ancestors 'none'",
      "object-src 'none'",
      "form-action 'self'",
      `connect-src 'self' ${uniqueExternalSources.join(" ")}`,
      `img-src 'self' data: blob: ${uniqueExternalSources.join(" ")} https://image.tmdb.org https://www.themoviedb.org`,
      `media-src 'self' blob: ${uniqueExternalSources.join(" ")}`,
      `script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'${process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : ""}${turnstileOrigin}`,
      `frame-src 'self'${turnstileOrigin}`,
      "style-src 'self' 'unsafe-inline'",
      "font-src 'self' data:",
    ].join("; ");
    return [
      {
        source: "/:path*",
        headers: [
        { key: "Content-Security-Policy", value: policy },
        { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        // Do not add includeSubDomains: this response can be served from a
        // customer-owned hostname whose sibling subdomains Aperture does not control.
        { key: "Strict-Transport-Security", value: "max-age=31536000" },
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "X-Frame-Options", value: "DENY" },
        ],
      },
      {
        source: "/studio/:path*",
        headers: [
          { key: "Cache-Control", value: "private, no-store, max-age=0, must-revalidate" },
          { key: "Pragma", value: "no-cache" },
          { key: "Expires", value: "0" },
          { key: "X-Robots-Tag", value: "noindex, nofollow, noarchive, nosnippet" },
        ],
      },
    ];
  },
};

export default nextConfig;
