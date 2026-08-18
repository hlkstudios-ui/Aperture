import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  async headers() {
    const apiOrigin = process.env.NEXT_PUBLIC_API_ORIGIN ?? "http://localhost:8000";
    const objectStorageOrigin =
      process.env.NEXT_PUBLIC_OBJECT_STORAGE_ORIGIN ?? "http://localhost:9000";
    const mediaOrigin = process.env.NEXT_PUBLIC_MEDIA_ORIGIN ?? apiOrigin;
    const externalSources = [apiOrigin, objectStorageOrigin, mediaOrigin]
      .filter((value) => /^https?:\/\//.test(value));
    const uniqueExternalSources = [...new Set(externalSources)];
    const policy = [
      "default-src 'self'",
      "base-uri 'self'",
      "frame-ancestors 'none'",
      "object-src 'none'",
      "form-action 'self'",
      `connect-src 'self' ${uniqueExternalSources.join(" ")}`,
      `img-src 'self' data: blob: ${uniqueExternalSources.join(" ")} https://image.tmdb.org`,
      `media-src 'self' blob: ${uniqueExternalSources.join(" ")}`,
      `script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'${process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : ""}`,
      "style-src 'self' 'unsafe-inline'",
      "font-src 'self' data:",
    ].join("; ");
    return [{
      source: "/:path*",
      headers: [
        { key: "Content-Security-Policy", value: policy },
        { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "X-Frame-Options", value: "DENY" },
      ],
    }];
  },
};

export default nextConfig;
