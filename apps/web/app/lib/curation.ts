import { catalogFetch } from "@/app/lib/catalog";

export type CuratedTitle = {
  item_id: string;
  title_id: string;
  kind: "movie" | "series";
  slug: string;
  title: string;
  short_description: string;
  position: number;
  note: string | null;
  completed: boolean;
};

export type Collection = {
  id: string;
  slug: string;
  title: string;
  description: string;
  kind: string;
  status: string;
  owner_profile_id: string | null;
  owner_profile_name: string | null;
  visibility: "private" | "unlisted" | "public";
  moderation_status: "pending" | "approved" | "rejected" | "removed";
  items: CuratedTitle[];
};

export type Journey = {
  id: string;
  slug: string;
  title: string;
  description: string;
  status: string;
  chapters: Array<{
    title: string;
    introduction: string | null;
    position: number;
    items: CuratedTitle[];
  }>;
  completed_items: number;
  total_items: number;
  completed: boolean;
};

export const collectionFetch = (path: string) => catalogFetch<Collection>(path);
export const journeyFetch = (path: string) => catalogFetch<Journey>(path);
