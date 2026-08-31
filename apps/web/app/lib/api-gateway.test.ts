import { describe, expect, it } from "vitest";

import {
  API_GATEWAY_PREFIX,
  apiGatewayPath,
  browserPlaybackUrl,
  isGatewayUrl,
} from "./api-gateway";

describe("same-origin API gateway", () => {
  it("maps API paths without accepting arbitrary origins", () => {
    expect(apiGatewayPath("/auth/me?fresh=1")).toBe("/api/gateway/auth/me?fresh=1");
    expect(() => apiGatewayPath("https://evil.example/auth/me")).toThrow(TypeError);
    expect(() => apiGatewayPath("//evil.example/auth/me")).toThrow(TypeError);
  });

  it("rewrites only API-owned playback media", () => {
    const upstream = "http://api:8000";
    const managed = "/playback/sources/source-1/media/master.m3u8?grant=1";

    expect(browserPlaybackUrl(managed, upstream)).toBe(`${API_GATEWAY_PREFIX}${managed}`);
    expect(browserPlaybackUrl(`${upstream}${managed}`, upstream)).toBe(`${API_GATEWAY_PREFIX}${managed}`);
    expect(
      browserPlaybackUrl(`https://licensed-cdn.example${managed}`, upstream),
    ).toBe(`https://licensed-cdn.example${managed}`);
    expect(browserPlaybackUrl("https://licensed-cdn.example/title/master.m3u8", upstream))
      .toBe("https://licensed-cdn.example/title/master.m3u8");
  });

  it("recognizes gateway media as same-origin session traffic", () => {
    const base = "https://cinema.example/watch/movies/example";
    expect(isGatewayUrl("/api/gateway/playback/source/media/master.m3u8", base)).toBe(true);
    expect(isGatewayUrl("https://cdn.example/master.m3u8", base)).toBe(false);
  });
});
