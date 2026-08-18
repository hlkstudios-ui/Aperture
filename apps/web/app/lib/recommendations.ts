import type { Movie, Series } from "@/app/lib/catalog";
import { customerAccountFetch } from "@/app/lib/account";

export type RecommendationReason =
  | "editorial"
  | "similar_genres"
  | "similar_themes"
  | "similar_tags"
  | "profile_genre_preference"
  | "popular_now"
  | "cold_start";

export type RecommendationItem = {
  kind: "movie" | "series";
  score: number;
  reasons: RecommendationReason[];
  movie: Movie | null;
  series: Series | null;
};

export type RecommendationResponse = {
  profile_id: string;
  strategy: "rules_v1" | "editorial_popularity_v1";
  personalized: boolean;
  cold_start: boolean;
  watched_titles_excluded: number;
  items: RecommendationItem[];
};

export type TasteAffinity = { key: string; label: string; weight: number; watched_titles: number };
export type TasteDna = {
  profile_id: string;
  derived_from: "persisted_watch_progress";
  watched_titles: number;
  completed_titles: number;
  completion_rate: number | null;
  average_runtime_minutes: number | null;
  confidence: "none" | "emerging" | "established";
  genres: TasteAffinity[];
  themes: TasteAffinity[];
  tags: TasteAffinity[];
  decades: TasteAffinity[];
  countries: TasteAffinity[];
  languages: TasteAffinity[];
  insights: string[];
};

export const reasonLabels: Record<RecommendationReason, string> = {
  editorial: "Selected by our editors",
  similar_genres: "Genres you return to",
  similar_themes: "Themes from your viewing",
  similar_tags: "Details similar to titles you watched",
  profile_genre_preference: "Matches your genre preferences",
  popular_now: "Popular with viewers now",
  cold_start: "A strong place to begin",
};

export function recommendationFetch(): Promise<RecommendationResponse> {
  return customerAccountFetch<RecommendationResponse>("/recommendations");
}

export function tasteDnaFetch(): Promise<TasteDna> {
  return customerAccountFetch<TasteDna>("/recommendations/taste-dna");
}
