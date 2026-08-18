"use server";

import { revalidatePath } from "next/cache";
import { adminCatalogFetch } from "@/app/lib/admin-catalog";

export type CollectionDraft = {
  id?: string;
  slug: string;
  title: string;
  description: string;
  kind: string;
  status: string;
  movieIds: string[];
};

export type JourneyDraft = {
  id?: string;
  slug: string;
  title: string;
  description: string;
  status: string;
  chapters: Array<{
    title: string;
    introduction: string;
    movieIds: string[];
  }>;
};

export async function saveCollectionAction(payload: CollectionDraft): Promise<void> {
  await adminCatalogFetch(
    payload.id ? `/admin/curation/collections/${payload.id}` : "/admin/curation/collections",
    {
      method: payload.id ? "PUT" : "POST",
      body: JSON.stringify({
        slug: payload.slug,
        title: payload.title,
        description: payload.description,
        kind: payload.kind,
        status: payload.status,
        items: payload.movieIds.map((movie_id) => ({ movie_id })),
      }),
    },
  );
  revalidatePath("/studio/curation");
  revalidatePath("/collections");
}

export async function saveJourneyAction(payload: JourneyDraft): Promise<void> {
  await adminCatalogFetch(
    payload.id ? `/admin/curation/journeys/${payload.id}` : "/admin/curation/journeys",
    {
      method: payload.id ? "PUT" : "POST",
      body: JSON.stringify({
        slug: payload.slug,
        title: payload.title,
        description: payload.description,
        status: payload.status,
        chapters: payload.chapters.map((chapter) => ({
          title: chapter.title,
          introduction: chapter.introduction || null,
          items: chapter.movieIds.map((movie_id) => ({ movie_id })),
        })),
      }),
    },
  );
  revalidatePath("/studio/curation");
  revalidatePath("/journeys");
}
