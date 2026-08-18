import { CatalogLibraryPage, type LibraryTitle } from "@/app/components/catalog-library-page";
import { catalogFetch, type Movie, type Series } from "@/app/lib/catalog";

export const metadata = { title: "Browse" };
export default async function BrowsePage() {
  const [movies, series] = await Promise.all([catalogFetch<Movie[]>("/catalog/movies?limit=100"), catalogFetch<Series[]>("/catalog/series?limit=100")]);
  const items: LibraryTitle[] = [...movies.map((title) => ({ title, kind: "movie" as const })), ...series.map((title) => ({ title, kind: "series" as const }))].sort((a, b) => (b.title.release_date ?? "").localeCompare(a.title.release_date ?? ""));
  return <CatalogLibraryPage eyebrow="The complete catalog" title="Browse" description="Movies and series together, ordered by release date." items={items} empty="The catalog is waiting for its first title." />;
}
