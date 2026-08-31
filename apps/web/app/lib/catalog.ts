import { forwardedGeoHeaders } from "@/app/lib/geo-headers";

export type NamedRecord = { id: string; name: string; slug: string };

export type Movie = {
  id: string;
  title: string;
  slug: string;
  original_title: string | null;
  short_description: string;
  synopsis: string;
  release_date: string | null;
  runtime_minutes: number;
  maturity_rating: string | null;
  status: "draft" | "ready" | "published" | "archived";
  publish_at: string | null;
  unpublish_at: string | null;
  rights_start_at: string | null;
  rights_end_at: string | null;
  original_language_code: string | null;
  country_code: string | null;
  allowed_territories: string[];
  franchise_id: string | null;
  metadata_provider: string | null;
  external_id: string | null;
  poster_url: string | null;
  backdrop_url: string | null;
  content_format: string | null;
  studios: string[];
  genres: NamedRecord[];
  themes: NamedRecord[];
  tags: NamedRecord[];
  created_at: string;
  updated_at: string;
};

export type Episode = {
  id: string;
  season_id: string;
  number: number;
  title: string;
  synopsis: string;
  runtime_minutes: number;
  release_date: string | null;
  still_url: string | null;
  status: string;
};

export type Season = {
  id: string;
  series_id: string;
  number: number;
  title: string | null;
  synopsis: string | null;
  episodes: Episode[];
};

export type Series = {
  id: string;
  title: string;
  slug: string;
  original_title: string | null;
  short_description: string;
  synopsis: string;
  release_date: string | null;
  maturity_rating: string | null;
  status: string;
  publish_at: string | null;
  unpublish_at: string | null;
  rights_start_at: string | null;
  rights_end_at: string | null;
  original_language_code: string | null;
  country_code: string | null;
  allowed_territories: string[];
  franchise_id: string | null;
  metadata_provider: string | null;
  external_id: string | null;
  poster_url: string | null;
  backdrop_url: string | null;
  is_ongoing: boolean | null;
  content_format: string | null;
  studios: string[];
  genres: NamedRecord[];
  seasons: Season[];
  created_at: string;
  updated_at: string;
};

export function seriesIsCurrentlyAiring(series: Series, asOf = new Date()): boolean {
  if (series.is_ongoing === true) return true;
  const currentDate = asOf.toISOString().slice(0, 10);
  return series.seasons.some((season) => season.episodes.some((episode) =>
    episode.status === "published"
      && Boolean(episode.release_date)
      && episode.release_date!.slice(0, 10) >= currentDate,
  ));
}

export type Credit = {
  id: string;
  person_id: string;
  character_id: string | null;
  company_id: string | null;
  role: string;
  billing_order: number | null;
};

export type Preview = {
  id: string;
  kind: "trailer" | "clip";
  title: string;
  external_url: string | null;
  duration_seconds: number | null;
};

export type FilmKnowledgeGraph = {
  root_id: string;
  derived_from: "normalized_verified_catalog";
  nodes: Array<{ id: string; kind: string; label: string; href: string | null; detail: string | null }>;
  edges: Array<{ id: string; source: string; target: string; label: string }>;
};

export type CreditDestination = {
  id: string; kind: "person" | "company"; name: string; slug: string;
  biography: string | null; country_code: string | null;
  titles: Array<{ id: string; kind: "movie" | "series" | "episode"; title: string; href: string; role: string; character_name: string | null }>;
};

const apiOrigin =
  process.env.API_ORIGIN ??
  "http://localhost:8000";

export async function catalogFetch<T>(path: string): Promise<T> {
  const liveSearch = path.startsWith("/catalog/search")
    || path.startsWith("/catalog/browse")
    || path.startsWith("/catalog/trending")
    || path.startsWith("/catalog/explore");
  const response = await fetch(`${apiOrigin}${path}`, {
    ...(liveSearch ? { cache: "no-store" as const } : { next: { revalidate: 300 } }),
    headers: await forwardedGeoHeaders(),
  });
  if (!response.ok) {
    const error = new Error(
      `Catalog request failed with status ${response.status}`,
    );
    Object.assign(error, { status: response.status });
    throw error;
  }
  return response.json() as Promise<T>;
}

export function releaseYear(value: string | null): string {
  return value ? new Date(value).getUTCFullYear().toString() : "Coming soon";
}

export function runtimeLabel(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return hours ? `${hours}h ${remainder}m` : `${minutes}m`;
}
