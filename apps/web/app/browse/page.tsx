import { BrowseExperience } from "@/app/browse/browse-experience";
import type { BrowseResponse, BrowseSearchResponse, BrowseSectionsResponse } from "@/app/browse/browse-types";
import { SiteHeader } from "@/app/components/site-header";
import { catalogFetch } from "@/app/lib/catalog";

export const metadata = {
  title: "Browse",
  description: "Explore one hundred specialist movie and series collections, curated for every mood.",
};

type BrowsePageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

const BROWSE_QUERY_KEYS = new Set([
  "q", "sort", "kind", "genre", "theme", "tag", "character", "language",
  "country", "content_format", "maturity_rating", "studio", "release_decade",
  "runtime_band", "airing", "release_year_from", "release_year_to",
  "runtime_minutes_min", "runtime_minutes_max",
]);

export default async function BrowsePage({ searchParams }: BrowsePageProps) {
  const incoming = await searchParams;
  const visibleParams = new URLSearchParams();
  for (const [key, rawValue] of Object.entries(incoming)) {
    if (!BROWSE_QUERY_KEYS.has(key)) continue;
    for (const value of Array.isArray(rawValue) ? rawValue : [rawValue]) {
      if (value !== undefined) visibleParams.append(key, value);
    }
  }
  const apiParams = new URLSearchParams(visibleParams);
  const query = visibleParams.get("q")?.trim() ?? "";
  const hasAdvancedFilters = [...visibleParams.keys()].some((key) => key !== "q" && !(key === "sort" && visibleParams.get(key) === "newest"));
  apiParams.set("page", "1");
  apiParams.set("page_size", hasAdvancedFilters ? "32" : "1");
  const [initial, initialSections, initialSearch] = await Promise.all([
    catalogFetch<BrowseResponse>(`/catalog/browse?${apiParams}`),
    catalogFetch<BrowseSectionsResponse>("/catalog/browse/sections?page=1&page_size=6&items_per_section=18"),
    query && !hasAdvancedFilters
      ? catalogFetch<BrowseSearchResponse>(`/catalog/search?q=${encodeURIComponent(query)}&page=1&page_size=32`)
      : Promise.resolve(null),
  ]);

  return (
    <>
      <SiteHeader />
      <BrowseExperience initial={initial} initialSections={initialSections} initialSearch={initialSearch} initialParams={visibleParams.toString()} />
    </>
  );
}
