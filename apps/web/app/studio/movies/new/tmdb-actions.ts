"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { adminCatalogFetch, CatalogActionError } from "@/app/lib/admin-catalog";

export type TmdbMovieResult = {
  id: string;
  title: string;
  original_title: string | null;
  release_date: string | null;
  short_description: string;
  poster_url: string | null;
  original_language_code: string | null;
};
export type TmdbSearchState = { error: string; query?: string; total?: number; results?: TmdbMovieResult[] };

export async function searchTmdbMovies(_: TmdbSearchState, form: FormData): Promise<TmdbSearchState> {
  const query = String(form.get("query") ?? "").trim();
  if (query.length < 2) return { error: "Enter at least two characters." };
  try {
    const response = await adminCatalogFetch<{ total: number; results: TmdbMovieResult[] }>(`/admin/tmdb/movies?q=${encodeURIComponent(query)}`);
    return { error: "", query, total: response.total, results: response.results };
  } catch (error) {
    return { error: error instanceof CatalogActionError ? error.detail : "Movie API search is unavailable." };
  }
}

export async function importTmdbMovie(form: FormData): Promise<void> {
  const externalId = String(form.get("tmdb_id") ?? "").trim();
  if (!externalId || externalId.length > 200) return;
  const result = await adminCatalogFetch<{ id: string }>("/admin/tmdb/movies/import", {
    method: "POST",
    body: JSON.stringify({ external_id: externalId }),
  });
  revalidatePath("/studio/movies");
  revalidatePath("/studio/content");
  redirect(`/studio/sources?target=movie:${result.id}&imported=aperture`);
}
