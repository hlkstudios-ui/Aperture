export type ExploreCriteria = {
  content_type: "all" | "movie" | "series" | "ova";
  query?: string | null;
  genre?: string | null;
  studio?: string | null;
  country_code?: string | null;
  original_language_code?: string | null;
  maturity_rating?: string | null;
  release_period: "all" | "2020s" | "2010s" | "classic";
  duration: "all" | "short" | "standard" | "long";
  airing: "all" | "ongoing" | "finished";
};

export type ExploreCardTitle = {
  id: string;
  kind: "movie" | "series";
  title: string;
  original_title: string | null;
  slug: string;
  short_description: string;
  release_date: string | null;
  maturity_rating: string | null;
  poster_url: string | null;
  content_format: string | null;
  country_code: string | null;
  original_language_code: string | null;
  studios: string[];
  genres: string[];
  duration_minutes: number | null;
  is_ongoing: boolean | null;
  season_count: number;
  episode_count: number;
  href: string;
  source: "local" | "aperture" | "tmdb";
  availability: string;
};

export type ExploreCard = {
  id: string;
  movie_id: string | null;
  series_id: string | null;
  position: number;
  title: ExploreCardTitle;
};

export type ExploreEntry = {
  id: string;
  label: string;
  description: string;
  icon: string;
  position: number;
  enabled?: boolean;
  criteria: ExploreCriteria;
  cards?: ExploreCard[];
  created_at?: string;
  updated_at?: string;
};
