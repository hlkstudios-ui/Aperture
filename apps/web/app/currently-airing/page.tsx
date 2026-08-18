import { CatalogLibraryPage } from "@/app/components/catalog-library-page";
import { catalogFetch, type Series } from "@/app/lib/catalog";

export const metadata = { title: "Currently Airing" };
export default async function CurrentlyAiringPage() {
  const series = await catalogFetch<Series[]>("/catalog/series?limit=100");
  const items = series.filter((title) => title.is_ongoing).map((title) => ({ title, kind: "series" as const }));
  return <CatalogLibraryPage eyebrow="Episodes still arriving" title="Currently airing" description="Ongoing series with new stories still to come." items={items} empty="No series are currently marked as ongoing." />;
}
