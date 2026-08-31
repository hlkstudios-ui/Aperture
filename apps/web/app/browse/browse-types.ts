export type BrowseKind = "movie" | "series";

export type BrowseItem = {
  id: string;
  kind: BrowseKind;
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
  season_count: number;
  episode_count: number;
  duration_minutes: number | null;
  is_ongoing: boolean | null;
  href: string;
  source: "local" | "aperture" | "tmdb";
  availability: string;
  backdrop_url?: string | null;
  vote_average?: number | null;
  vote_count?: number | null;
  popularity?: number | null;
};

export type BrowseSection = {
  id: string;
  slug: string;
  eyebrow: string;
  title: string;
  description: string;
  media_type: "movie" | "series" | "mixed";
  source: "aperture" | "tmdb";
  status: "ready" | "stale" | "unavailable";
  items: BrowseItem[];
};

export type BrowseSectionsResponse = {
  page: number;
  page_size: number;
  total_sections: number;
  has_more: boolean;
  next_page: number | null;
  items_per_section: number;
  sections: BrowseSection[];
  attribution: {
    provider: "TMDB";
    notice: string;
    url: string;
  };
  partial: boolean;
};

export type TrendingTitlesResponse = {
  page: number;
  page_size: number;
  total_results: number;
  total_pages: number;
  has_more: boolean;
  next_page: number | null;
  source: "aperture" | "tmdb";
  status: "ready" | "unavailable";
  items: BrowseItem[];
  attribution: BrowseSectionsResponse["attribution"];
};

export type BrowseSearchResponse = {
  query: string;
  page: number;
  page_size: number;
  total_titles: number;
  total_entities: number;
  has_more: boolean;
  titles: BrowseItem[];
  entities: Array<{
    id: string;
    kind: string;
    name: string;
    slug: string;
    detail: string | null;
    href: string | null;
  }>;
};

export type BrowseFacet = {
  key: string;
  label: string;
  icon: string;
  selection: "multiple" | "single";
  options: BrowseFacetOption[];
};

export type BrowseFacetOption = {
  value: string;
  label: string;
  count: number;
};

export type BrowseFacetGroup = {
  key: string;
  label: string;
  icon: string;
  facets: BrowseFacet[];
};

export type BrowseResponse = {
  query: string | null;
  page: number;
  page_size: number;
  total: number;
  has_more: boolean;
  next_page: number | null;
  sort: "newest" | "oldest" | "title_asc" | "title_desc";
  items: BrowseItem[];
  facet_groups: BrowseFacetGroup[];
};

export type BrowseFilters = {
  kind: "" | BrowseKind;
  genres: string[];
  themes: string[];
  tags: string[];
  languages: string[];
  countries: string[];
  contentFormats: string[];
  maturityRatings: string[];
  studios: string[];
  releaseDecades: string[];
  runtimeBands: string[];
  yearMin: string;
  yearMax: string;
  runtimeMin: string;
  runtimeMax: string;
  airing: "" | "ongoing" | "completed";
  sort: "newest" | "oldest" | "title_asc" | "title_desc";
};

export const EMPTY_BROWSE_FILTERS: BrowseFilters = {
  kind: "",
  genres: [],
  themes: [],
  tags: [],
  languages: [],
  countries: [],
  contentFormats: [],
  maturityRatings: [],
  studios: [],
  releaseDecades: [],
  runtimeBands: [],
  yearMin: "",
  yearMax: "",
  runtimeMin: "",
  runtimeMax: "",
  airing: "",
  sort: "newest",
};
