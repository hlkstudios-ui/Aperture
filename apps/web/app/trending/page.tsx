import { CatalogLibraryPage, type LibraryTitle } from "@/app/components/catalog-library-page";
import { catalogFetch, type Movie, type Series } from "@/app/lib/catalog";

export const metadata = { title: "Trending" };
export default async function TrendingPage() {
  const [movies, series] = await Promise.all([catalogFetch<Movie[]>("/catalog/movies?limit=20"), catalogFetch<Series[]>("/catalog/series?limit=20")]);
  const items: LibraryTitle[] = [...movies.slice(0, 10).map((title) => ({ title, kind: "movie" as const })), ...series.slice(0, 10).map((title) => ({ title, kind: "series" as const }))];
  return <CatalogLibraryPage eyebrow="Editorial spotlight" title="Trending" description="A transparent editorial selection until sufficient first-party viewing activity is available for a genuine trend chart." items={items} empty="No titles are available for the spotlight." />;
}
