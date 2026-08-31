import { NextRequest, NextResponse } from "next/server";
import { catalogFetch } from "@/app/lib/catalog";
import type { BrowseResponse } from "@/app/browse/browse-types";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const query = request.nextUrl.searchParams.toString();

  try {
    const result = await catalogFetch<BrowseResponse>(
      `/catalog/browse${query ? `?${query}` : ""}`,
    );
    return NextResponse.json(result, {
      headers: { "Cache-Control": "private, no-store" },
    });
  } catch (error) {
    const status =
      typeof error === "object" && error !== null && "status" in error
        ? Number(error.status)
        : 503;
    return NextResponse.json(
      { detail: "The Browse catalog is temporarily unavailable." },
      { status: Number.isInteger(status) && status >= 400 && status <= 599 ? status : 503 },
    );
  }
}
