import { catalogFetch } from "@/app/lib/catalog";
import { forwardedGeoHeaders } from "@/app/lib/geo-headers";
import { cookies } from "next/headers";

export type HomepageTitle = {
  id: string;
  kind: "movie" | "series";
  title: string;
  slug: string;
  short_description: string;
  maturity_rating: string | null;
  runtime_minutes: number | null;
  poster_url: string | null;
  backdrop_url: string | null;
  metadata_provider: string | null;
};

export type PublicHomepage = {
  hero: HomepageTitle | null;
  rails: Array<{
    id: string;
    title: string;
    eyebrow: string | null;
    items: HomepageTitle[];
  }>;
  published_at: string | null;
  mode: "curated" | "no_algorithm";
  strategy: "published_editorial_snapshot" | "deterministic_catalog_indexes_v1";
};

export type HomepageItem = {
  id: string;
  movie_id: string | null;
  series_id: string | null;
  position: number;
};

export type HomepageRail = {
  id: string;
  title: string;
  eyebrow: string | null;
  source: "pinned" | "latest_movies" | "latest_series" | "mixed";
  query: string | null;
  position: number;
  enabled: boolean;
  starts_at: string | null;
  ends_at: string | null;
  items: HomepageItem[];
};

export type HomepageDraft = {
  id: string;
  hero_movie_id: string | null;
  hero_series_id: string | null;
  rails: HomepageRail[];
  published_at: string | null;
};

export function homepageFetch(): Promise<PublicHomepage> {
  return catalogFetch<PublicHomepage>("/homepage");
}

export async function profileHomepageFetch(): Promise<PublicHomepage | null> {
  let cookieStore: Awaited<ReturnType<typeof cookies>>;
  try {
    cookieStore = await cookies();
  } catch {
    return null;
  }
  const session = cookieStore.get("aperture_session");
  if (!session) return null;
  const response = await fetch(
    `${process.env.API_ORIGIN ?? "http://localhost:8000"}/homepage/profile`,
    {
      cache: "no-store",
      headers: {
        cookie: `${session.name}=${session.value}`,
        ...(await forwardedGeoHeaders()),
      },
    },
  );
  if (!response.ok) return null;
  return response.json() as Promise<PublicHomepage>;
}
