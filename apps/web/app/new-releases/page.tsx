import { CatalogLibraryPage, type LibraryTitle } from "@/app/components/catalog-library-page";
import { catalogFetch, type Movie, type Series } from "@/app/lib/catalog";

export const metadata = { title: "New Releases" };
export default async function NewReleasesPage() {
  const [movies, series] = await Promise.all([catalogFetch<Movie[]>("/catalog/movies?limit=50"), catalogFetch<Series[]>("/catalog/series?limit=50")]);
  const items: LibraryTitle[] = [...movies.map((title) => ({ title, kind: "movie" as const })), ...series.map((title) => ({ title, kind: "series" as const }))].sort((a, b) => (b.title.release_date ?? "").localeCompare(a.title.release_date ?? "")).slice(0, 40);
  return <CatalogLibraryPage eyebrow="Fresh from the catalog" title="New releases" description="The latest published movies and series, with the newest releases first." items={items} empty="No new releases are available yet." />;
}
