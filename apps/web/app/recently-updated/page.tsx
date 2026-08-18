import { CatalogLibraryPage, type LibraryTitle } from "@/app/components/catalog-library-page";
import { catalogFetch, type Movie, type Series } from "@/app/lib/catalog";

export const metadata = { title: "Recently Updated" };
export default async function RecentlyUpdatedPage() {
  const [movies, series] = await Promise.all([catalogFetch<Movie[]>("/catalog/movies?limit=100"), catalogFetch<Series[]>("/catalog/series?limit=100")]);
  const items: LibraryTitle[] = [...movies.map((title) => ({ title, kind: "movie" as const })), ...series.map((title) => ({ title, kind: "series" as const }))].sort((a, b) => b.title.updated_at.localeCompare(a.title.updated_at)).slice(0, 40);
  return <CatalogLibraryPage eyebrow="Catalog activity" title="Recently updated" description="Titles with the most recent verified catalog changes." items={items} empty="No recent catalog updates are available." />;
}
