import { customerAccountFetch } from "@/app/lib/account";

export type Distribution = { key: string; label: string; count: number; percentage: number };
export type Creator = { person_id: string; name: string; roles: string[]; completed_views: number };
export type PassportReport = {
  profile_id: string;
  year: number | null;
  available_years: number[];
  generated_from: "viewing_activities";
  privacy: "private_to_profile";
  films_watched: number;
  episodes_watched: number;
  completed_views: number;
  first_watches: number;
  rewatches: number;
  observed_watch_hours: number;
  countries_explored: number;
  longest_title: string | null;
  shortest_title: string | null;
  favorite_genres: Distribution[];
  favorite_creators: Creator[];
  country_distribution: Distribution[];
  decade_distribution: Distribution[];
  history: Array<{ kind: "movie" | "episode"; title: string; parent_title: string | null; activity_number: number; is_rewatch: boolean; watched_seconds: number; completed: boolean; started_at: string; completed_at: string | null }>;
  milestones: string[];
};

export function passportFetch(year?: number): Promise<PassportReport> {
  return customerAccountFetch<PassportReport>(`/passport${year ? `?year=${year}` : ""}`);
}
