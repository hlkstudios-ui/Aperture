import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import type { NamedRecord } from "@/app/lib/catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { MovieForm } from "@/app/studio/components/movie-form";
import { StudioShell } from "@/app/studio/components/studio-shell";
import { TmdbMovieSearch } from "./tmdb-movie-search";

export const metadata = { title: "New movie · Studio" };
export default async function NewMovie({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const admin = await requireAdminSession();
  const { q = "" } = await searchParams;
  const [genres, themes, tags] = await Promise.all([
    adminCatalogFetch<NamedRecord[]>("/admin/catalog/named/genres"),
    adminCatalogFetch<NamedRecord[]>("/admin/catalog/named/themes"),
    adminCatalogFetch<NamedRecord[]>("/admin/catalog/named/tags"),
  ]);
  return (
    <StudioShell
      admin={admin}
      active="movies"
      eyebrow="Catalog acquisition"
      title="Add a movie"
    >
      <TmdbMovieSearch initialQuery={q.slice(0, 120)} />
      <details className="manual-movie-entry">
        <summary>Can’t find it on TMDB? Create an original record</summary>
        <div className="editor-intro"><p>Use manual entry for original productions, private screeners, or titles that are not represented by TMDB. Every record remains private until deliberately published.</p></div>
        <MovieForm genres={genres} themes={themes} tags={tags} />
      </details>
    </StudioShell>
  );
}
