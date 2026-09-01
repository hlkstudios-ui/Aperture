import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GET, POST } from "./route";

const API_ORIGIN = "http://127.0.0.1:18001";

function context(path?: string[]) {
  return { params: Promise.resolve({ path }) };
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("same-origin API gateway", () => {
  it("forwards only the allowlisted platform control-plane namespace", async () => {
    vi.stubEnv("API_ORIGIN", API_ORIGIN);
    const fetchMock = vi.fn(async (_target: URL | RequestInfo, _init?: RequestInit) => {
      void _target;
      void _init;
      return Response.json({ schema_version: 1, items: [] });
    });
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(
      new NextRequest("https://apertures.online/api/gateway/platform/templates"),
      context(["platform", "templates"]),
    );

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(String(fetchMock.mock.calls[0][0])).toBe(`${API_ORIGIN}/platform/templates`);
  });

  it("rejects non-allowlisted and traversal paths before an upstream request", async () => {
    vi.stubEnv("API_ORIGIN", API_ORIGIN);
    vi.stubEnv("CUSTOM_DOMAIN_EDGE_SECRET", "server-side-edge-secret");
    vi.stubGlobal("fetch", vi.fn());

    const forbidden = await GET(
      new NextRequest("https://cinema.example/api/gateway/ready"),
      context(["ready"]),
    );
    const traversal = await GET(
      new NextRequest("https://cinema.example/api/gateway/auth/../ready"),
      context(["auth", "..", "ready"]),
    );

    expect(forbidden.status).toBe(404);
    expect(traversal.status).toBe(404);
    expect(forbidden.headers.get("cache-control")).toBe(
      "private, no-store, max-age=0, must-revalidate",
    );
    expect(forbidden.headers.get("vary")).toContain("Cookie");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("streams the request and preserves OAuth redirects and separate cookies", async () => {
    vi.stubEnv("API_ORIGIN", API_ORIGIN);
    vi.stubEnv("CUSTOM_DOMAIN_EDGE_SECRET", "server-side-edge-secret");
    let forwardedBody = "";
    const upstreamHeaders = new Headers({
      Location: "https://identity.example/authorize?state=safe",
      Vary: "Origin, Accept-Encoding",
    });
    upstreamHeaders.append("Set-Cookie", "oauth_state=one; Path=/api/gateway/auth; HttpOnly");
    upstreamHeaders.append("Set-Cookie", "device=two; Path=/; Secure; SameSite=Lax");
    const fetchMock = vi.fn(async (_target: URL | RequestInfo, init?: RequestInit) => {
      forwardedBody = await new Response(init?.body).text();
      return new Response(null, { status: 302, headers: upstreamHeaders });
    });
    vi.stubGlobal("fetch", fetchMock);

    const payload = JSON.stringify({ email: "owner@example.com" });
    const request = new NextRequest(
      "https://cinema.example/api/gateway/auth/login?remember=1",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Cookie: "remembered=yes",
          Origin: "https://cinema.example",
          "X-Aperture-Public-Origin": "https://spoofed.example",
          "X-Aperture-Edge-Secret": "browser-supplied-secret",
          "X-Aperture-Studio-Edge": "must-not-reach-the-api",
        },
        body: payload,
      },
    );
    const response = await POST(request, context(["auth", "login"]));

    expect(fetchMock).toHaveBeenCalledOnce();
    const [target, init] = fetchMock.mock.calls[0];
    expect(String(target)).toBe(`${API_ORIGIN}/auth/login?remember=1`);
    const headers = new Headers(init?.headers);
    expect(headers.get("cookie")).toBe("remembered=yes");
    expect(headers.get("origin")).toBe("https://cinema.example");
    expect(headers.get("x-aperture-public-origin")).toBe("https://cinema.example");
    expect(headers.get("x-aperture-edge-secret")).toBe("server-side-edge-secret");
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.get("accept-encoding")).toBe("identity");
    expect(headers.get("x-aperture-studio-edge")).toBeNull();
    expect(init?.redirect).toBe("manual");
    expect(init?.cache).toBe("no-store");
    expect((init as RequestInit & { duplex?: string }).duplex).toBe("half");
    expect(forwardedBody).toBe(payload);

    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe(
      "https://identity.example/authorize?state=safe",
    );
    expect(response.headers.getSetCookie()).toEqual([
      "oauth_state=one; Path=/api/gateway/auth; HttpOnly",
      "device=two; Path=/; Secure; SameSite=Lax",
    ]);
    expect(response.headers.get("cache-control")).toBe(
      "private, no-store, max-age=0, must-revalidate",
    );
    expect(response.headers.get("pragma")).toBe("no-cache");
    expect(response.headers.get("expires")).toBe("0");
    expect(response.headers.get("vary")).toBe("Origin, Accept-Encoding, Cookie");
  });

  it("streams media ranges while preserving range response metadata", async () => {
    vi.stubEnv("API_ORIGIN", API_ORIGIN);
    const bytes = new Uint8Array([4, 8, 15, 16, 23, 42]);
    const fetchMock = vi.fn(async (_target: URL | RequestInfo, init?: RequestInit) => {
      expect(new Headers(init?.headers).get("range")).toBe("bytes=100-105");
      return new Response(bytes, {
        status: 206,
        headers: {
          "Accept-Ranges": "bytes",
          "Content-Range": "bytes 100-105/1000",
          "Content-Type": "video/mp4",
          "Content-Length": String(bytes.byteLength),
          "Content-Encoding": "gzip",
        },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(
      new NextRequest(
        "https://cinema.example/api/gateway/playback/sources/source-1/media/segment.mp4",
        { headers: { Range: "bytes=100-105", Cookie: "session=valid" } },
      ),
      context(["playback", "sources", "source-1", "media", "segment.mp4"]),
    );

    expect(response.status).toBe(206);
    expect(response.headers.get("accept-ranges")).toBe("bytes");
    expect(response.headers.get("content-range")).toBe("bytes 100-105/1000");
    expect(response.headers.get("content-type")).toBe("video/mp4");
    expect(response.headers.get("content-length")).toBeNull();
    expect(response.headers.get("content-encoding")).toBeNull();
    expect(response.headers.get("server")).toBeNull();
    expect(new Uint8Array(await response.arrayBuffer())).toEqual(bytes);
  });

  it("preserves the edge-asserted customer hostname after the origin rewrite", async () => {
    vi.stubEnv("API_ORIGIN", API_ORIGIN);
    vi.stubEnv("CUSTOM_DOMAIN_EDGE_SECRET", "server-side-edge-secret");
    const fetchMock = vi.fn(
      async (target: URL | RequestInfo, init?: RequestInit) => {
        void target;
        void init;
        return Response.json({ ok: true });
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    await GET(
      new NextRequest("https://origin.apertures.online/api/gateway/auth/providers", {
        headers: {
          "X-Aperture-Public-Host": "watch.customer.example",
          "X-Forwarded-Proto": "https",
        },
      }),
      context(["auth", "providers"]),
    );

    const [, init] = fetchMock.mock.calls[0];
    const headers = new Headers(init?.headers);
    expect(headers.get("x-aperture-public-origin")).toBe(
      "https://watch.customer.example",
    );
    expect(headers.get("x-aperture-public-host")).toBe("watch.customer.example");
  });
});
