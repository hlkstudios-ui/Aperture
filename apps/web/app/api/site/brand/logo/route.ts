import { NextRequest, NextResponse } from "next/server";

const apiOrigin = process.env.API_ORIGIN ?? "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const revision = request.nextUrl.searchParams.get("revision");
  if (revision !== null && !/^\d+$/.test(revision)) {
    return NextResponse.json({ detail: "Invalid logo revision" }, { status: 400 });
  }
  const upstream = await fetch(
    `${apiOrigin.replace(/\/$/, "")}/site/brand/logo${revision === null ? "" : `?revision=${revision}`}`,
    {
      cache: "no-store",
      headers: request.headers.get("if-none-match")
        ? { "If-None-Match": request.headers.get("if-none-match") as string }
        : undefined,
    },
  ).catch(() => null);
  if (!upstream) return new NextResponse(null, { status: 503 });
  if (upstream.status === 304) {
    return new NextResponse(null, {
      status: 304,
      headers: {
        "Cache-Control": upstream.headers.get("cache-control") ?? "public, max-age=300, stale-while-revalidate=86400",
        ETag: upstream.headers.get("etag") ?? "",
      },
    });
  }
  if (!upstream.ok || !upstream.body) {
    return new NextResponse(null, { status: upstream.status === 404 ? 404 : 502 });
  }
  return new NextResponse(upstream.body, {
    headers: {
      "Cache-Control": upstream.headers.get("cache-control") ?? "public, max-age=300, stale-while-revalidate=86400",
      "Content-Type": upstream.headers.get("content-type") ?? "application/octet-stream",
      "X-Content-Type-Options": "nosniff",
      ...(upstream.headers.get("etag") ? { ETag: upstream.headers.get("etag") as string } : {}),
    },
  });
}
