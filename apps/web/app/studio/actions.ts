"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { adminCatalogFetch, CatalogActionError } from "@/app/lib/admin-catalog";
import type { Movie, Series } from "@/app/lib/catalog";

export type FormState = { error: string; success?: string };

function text(form: FormData, key: string): string {
  return String(form.get(key) ?? "").trim();
}
function optional(form: FormData, key: string): string | null {
  return text(form, key) || null;
}
function numberValue(form: FormData, key: string): number {
  return Number(text(form, key));
}
function territories(form: FormData): string[] {
  return text(form, "allowed_territories")
    .split(",")
    .map((country) => country.trim().toUpperCase())
    .filter(Boolean);
}
function message(error: unknown): string {
  return error instanceof CatalogActionError
    ? error.detail
    : "The catalog service could not complete this action.";
}

function moviePayload(form: FormData) {
  return {
    title: text(form, "title"),
    slug: text(form, "slug"),
    original_title: optional(form, "original_title"),
    short_description: text(form, "short_description"),
    synopsis: text(form, "synopsis"),
    release_date: optional(form, "release_date"),
    runtime_minutes: numberValue(form, "runtime_minutes"),
    maturity_rating: optional(form, "maturity_rating"),
    original_language_code: optional(form, "original_language_code"),
    country_code: optional(form, "country_code"),
    allowed_territories: territories(form),
    genre_ids: form.getAll("genre_ids").map(String),
    theme_ids: form.getAll("theme_ids").map(String),
    tag_ids: form.getAll("tag_ids").map(String),
  };
}

export async function createMovieAction(
  _: FormState,
  form: FormData,
): Promise<FormState> {
  let movie: Movie;
  try {
    movie = await adminCatalogFetch<Movie>("/admin/catalog/movies", {
      method: "POST",
      body: JSON.stringify({ ...moviePayload(form), status: "draft" }),
    });
  } catch (error) {
    return { error: message(error) };
  }
  revalidatePath("/studio/content");
  revalidatePath("/studio/movies");
  redirect(`/studio/movies/${movie.id}?created=1`);
}

export async function updateMovieAction(
  movieId: string,
  _: FormState,
  form: FormData,
): Promise<FormState> {
  try {
    await adminCatalogFetch(`/admin/catalog/movies/${movieId}`, {
      method: "PATCH",
      body: JSON.stringify(moviePayload(form)),
    });
  } catch (error) {
    return { error: message(error) };
  }
  revalidatePath(`/studio/movies/${movieId}`);
  revalidatePath("/studio/content");
  return { error: "", success: "Metadata saved" };
}

export async function setMovieStatusAction(
  movieId: string,
  status: string,
): Promise<void> {
  await adminCatalogFetch(`/admin/catalog/movies/${movieId}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
  revalidatePath(`/studio/movies/${movieId}`);
  revalidatePath("/studio/content");
  revalidatePath("/");
}

export async function createTitleRelationshipAction(form: FormData): Promise<void> {
  await adminCatalogFetch("/admin/catalog/title-relationships", {
    method: "POST",
    body: JSON.stringify({
      source_movie_id: text(form, "source_movie_id"),
      target_movie_id: text(form, "target_movie_id"),
      kind: text(form, "kind"),
      description: optional(form, "description"),
      source_note: text(form, "source_note"),
      manually_verified: form.get("manually_verified") === "on",
    }),
  });
  revalidatePath("/studio/knowledge");
  revalidatePath("/movies");
}

export async function deleteTitleRelationshipAction(id: string): Promise<void> {
  await adminCatalogFetch(`/admin/catalog/title-relationships/${id}`, { method: "DELETE" });
  revalidatePath("/studio/knowledge");
  revalidatePath("/movies");
}

export async function addArtworkAction(
  movieId: string,
  _: FormState,
  form: FormData,
): Promise<FormState> {
  try {
    await adminCatalogFetch("/admin/catalog/artwork", {
      method: "POST",
      body: JSON.stringify({
        movie_id: movieId,
        kind: text(form, "kind"),
        storage_key: text(form, "storage_key"),
        alt_text: text(form, "alt_text"),
        width: optional(form, "width") ? numberValue(form, "width") : null,
        height: optional(form, "height") ? numberValue(form, "height") : null,
      }),
    });
  } catch (error) {
    return { error: message(error) };
  }
  revalidatePath(`/studio/movies/${movieId}`);
  return { error: "", success: "Artwork reference added" };
}

export async function createSeriesAction(
  _: FormState,
  form: FormData,
): Promise<FormState> {
  let series: Series;
  try {
    series = await adminCatalogFetch<Series>("/admin/catalog/series", {
      method: "POST",
      body: JSON.stringify({
        title: text(form, "title"),
        slug: text(form, "slug"),
        short_description: text(form, "short_description"),
        synopsis: text(form, "synopsis"),
        release_date: optional(form, "release_date"),
        maturity_rating: optional(form, "maturity_rating"),
        allowed_territories: territories(form),
        status: "draft",
        genre_ids: form.getAll("genre_ids").map(String),
      }),
    });
  } catch (error) {
    return { error: message(error) };
  }
  revalidatePath("/studio/series");
  revalidatePath("/studio/content");
  redirect(`/studio/series/${series.id}?created=1`);
}

export async function setSeriesStatusAction(
  seriesId: string,
  status: string,
): Promise<void> {
  await adminCatalogFetch(`/admin/catalog/series/${seriesId}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
  revalidatePath(`/studio/series/${seriesId}`);
  revalidatePath("/studio/content");
  revalidatePath("/");
}

export async function updateSeriesTerritoriesAction(
  seriesId: string,
  _: FormState,
  form: FormData,
): Promise<FormState> {
  try {
    await adminCatalogFetch(`/admin/catalog/series/${seriesId}`, {
      method: "PATCH",
      body: JSON.stringify({ allowed_territories: territories(form) }),
    });
  } catch (error) {
    return { error: message(error) };
  }
  revalidatePath(`/studio/series/${seriesId}`);
  revalidatePath("/");
  return { error: "", success: "Series territories saved" };
}

export async function updateEditionTerritoriesAction(
  editionId: string,
  form: FormData,
): Promise<void> {
  await adminCatalogFetch(`/admin/catalog/editions/${editionId}`, {
    method: "PATCH",
    body: JSON.stringify({ allowed_territories: territories(form) }),
  });
  revalidatePath("/studio/movies");
  revalidatePath("/");
}

export async function scheduleTitleAction(
  kind: "movies" | "series",
  id: string,
  _: FormState,
  form: FormData,
): Promise<FormState> {
  const instant = (key: string) => {
    const raw = optional(form, key);
    return raw ? `${raw}:00Z` : null;
  };
  try {
    await adminCatalogFetch(`/admin/catalog/${kind}/${id}`, {
      method: "PATCH",
      body: JSON.stringify({
        publish_at: instant("publish_at"),
        unpublish_at: instant("unpublish_at"),
        rights_start_at: instant("rights_start_at"),
        rights_end_at: instant("rights_end_at"),
      }),
    });
  } catch (error) {
    return { error: message(error) };
  }
  revalidatePath(`/studio/${kind}/${id}`);
  revalidatePath("/");
  return { error: "", success: "UTC availability schedule saved" };
}

export async function addSeasonAction(
  seriesId: string,
  _: FormState,
  form: FormData,
): Promise<FormState> {
  try {
    await adminCatalogFetch("/admin/catalog/seasons", {
      method: "POST",
      body: JSON.stringify({
        series_id: seriesId,
        number: numberValue(form, "number"),
        title: optional(form, "title"),
        synopsis: optional(form, "synopsis"),
      }),
    });
  } catch (error) {
    return { error: message(error) };
  }
  revalidatePath(`/studio/series/${seriesId}`);
  return { error: "", success: "Season created" };
}

export async function addEpisodeAction(
  seriesId: string,
  _: FormState,
  form: FormData,
): Promise<FormState> {
  try {
    await adminCatalogFetch("/admin/catalog/episodes", {
      method: "POST",
      body: JSON.stringify({
        season_id: text(form, "season_id"),
        number: numberValue(form, "number"),
        title: text(form, "title"),
        synopsis: text(form, "synopsis"),
        runtime_minutes: numberValue(form, "runtime_minutes"),
        release_date: optional(form, "release_date"),
        status: "draft",
      }),
    });
  } catch (error) {
    return { error: message(error) };
  }
  revalidatePath(`/studio/series/${seriesId}`);
  return { error: "", success: "Episode created" };
}

export async function bulkEpisodesAction(
  seriesId: string,
  _: FormState,
  form: FormData,
): Promise<FormState> {
  const seasonId = text(form, "season_id");
  const lines = text(form, "episodes")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (!lines.length) return { error: "Add at least one episode line." };
  for (const [index, line] of lines.entries()) {
    const [number, title, runtime, ...synopsis] = line
      .split("|")
      .map((part) => part.trim());
    if (!number || !title || !runtime || !synopsis.length)
      return {
        error: `Line ${index + 1} must use number | title | runtime | synopsis.`,
      };
    try {
      await adminCatalogFetch("/admin/catalog/episodes", {
        method: "POST",
        body: JSON.stringify({
          season_id: seasonId,
          number: Number(number),
          title,
          runtime_minutes: Number(runtime),
          synopsis: synopsis.join(" | "),
          status: "draft",
        }),
      });
    } catch (error) {
      return { error: `Line ${index + 1}: ${message(error)}` };
    }
  }
  revalidatePath(`/studio/series/${seriesId}`);
  return { error: "", success: `${lines.length} episodes created` };
}
